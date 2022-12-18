import random
from collections import deque

import pygame
import json

from keras.models import Sequential
from keras.layers import Dense, Dropout, Conv2D, MaxPooling2D, Activation, Flatten, Embedding, Reshape
from keras.callbacks import TensorBoard
from keras.optimizers import Adam
from collections import deque
import numpy as np
import tensorflow as tf
import time
from global_data import HyperParameters
from tensorflow import float32


class Controls:

    def get_action(self, state):
        pass

    def learn(self):
        pass


class RandomControls(Controls):

    def get_action(self, state=None):
        return random.randint(0, 3)


class PlayerControls(Controls):

    def get_action(self, state=None):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            return 0
        elif keys[pygame.K_LEFT]:
            return 1
        elif keys[pygame.K_RIGHT]:
            return 2
        elif keys[pygame.K_SPACE]:
            return 3
        else:
            return 0



class QLearningControls(Controls):

    def __init__(self, directory):
        self.Q_Table = {}
        self.directory = directory
        self.replay_memory = list()
        self.rewards = list()

    def state_to_key(self, state):
        state[0] = round(state[0], 1)
        state[1] = round(state[1], 1)
        state[2] = round(state[2], 1)
        return str(state)

    def get_action(self, state):
        key = self.state_to_key(state)
        row = self.Q_Table.get(key)
        if row is None:
            row = [random.random() for _ in range(HyperParameters.action_size)]
            self.Q_Table[key] = row
        if random.random() < HyperParameters.epsilon:
            return random.randint(0, HyperParameters.action_size-1)
        return np.argmax(row)

    def store(self, state, action, reward, next_state):
        self.replay_memory.append((state, action, reward, next_state))
        self.rewards.append(reward)

    def learn(self):
        for (state, action, reward, next_state) in self.replay_memory:
            key = self.state_to_key(state)
            row = self.Q_Table.get(key) or [random.random() for _ in range(HyperParameters.action_size)]
            self.Q_Table[key] = row
            old_q = row[action]
            next_key = self.state_to_key(next_state)
            next_row = self.Q_Table.get(next_key) or [random.random() for _ in range(HyperParameters.action_size)]
            self.Q_Table[next_key] = next_row
            max_q = max(next_row)
            row[action] = HyperParameters.inverse_alpha * old_q + HyperParameters.learning_rate * (reward + HyperParameters.discount * max_q)
        self.replay_memory.clear()

    def print_table(self):
        print(json.dumps(self.Q_Table, indent=2))

    def calculate_stats(self):
        stats = sum(self.rewards) / len(self.rewards), min(self.rewards), max(self.rewards)
        self.rewards.clear()
        return stats

    def save(self, file):
        serialized = json.dumps(self.Q_Table, indent=2)
        with open(f"{self.directory}/{file}{HyperParameters.episode}", "w") as f:
            f.write(serialized)

    def load(self, file):
        try:
            with open(f"{self.directory}/{file}", "r") as f:
                self.Q_Table = json.load(f)
        except:
            pass


class ModifiedTensorBoard(TensorBoard):

    # Overriding init to set initial step and writer (we want one log file for all .fit() calls)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.step = 1
        self.writer = tf.summary.create_file_writer(self.log_dir)

    # Overriding this method to stop creating default log writer
    def set_model(self, model):
        pass

    # Overrided, saves logs with our step number
    # (otherwise every .fit() will start writing from 0th step)
    def on_epoch_end(self, epoch, logs=None):
        self.update_stats(**logs)

    # Overrided
    # We train for one batch only, no need to save anything at epoch end
    def on_batch_end(self, batch, logs=None):
        pass

    # Overrided, so won't close writer
    def on_train_end(self, logs=None):
        pass

    # Custom method for saving own metrics
    # Creates writer, writes custom metrics and closes writer
    def update_stats(self, **stats):
        self._write_logs(stats, self.step)


class DeepQLearningControls(Controls):
    MEMORY_SIZE = 1_000_000
    BATCH_SIZE = 64_000
    UPDATE_LIMIT = 2

    def __init__(self, directory):
        self.directory = directory
        self.replay_memory = deque()

        self.model = self.build_compile_model()
        self.target_model = self.build_compile_model()
        self.align_target_model()
        self.rewards = list()

        # self.tensorboard = ModifiedTensorBoard(log_dir="logs/{}-{}".format("Deeeep", int(time.time())))

        self.target_update_counter = 0

    def store(self, state, action, reward, next_state):
        self.replay_memory.append((state, action, reward, next_state))
        self.rewards.append(reward)

    def build_compile_model(self):
        model = Sequential()
        model.add(Dense(7, input_shape=[7], activation='relu'))
        model.add(Dense(7, activation='relu'))
        model.add(Dense(7, activation='relu'))
        model.add(Dense(7, activation='relu'))
        # model.add(Dense(64, activation='relu'))
        model.add(Dense(4, activation='sigmoid'))

        model.compile(loss="mse", optimizer=Adam(learning_rate=HyperParameters.learning_rate), metrics=['accuracy'])
        return model

    def align_target_model(self):
        self.target_model.set_weights(self.model.get_weights())

    def get_action(self, state):
        if random.random() < HyperParameters.epsilon:
            return random.randint(0, 3)
        qs = self.get_qs(state)
        action = np.argmax(qs)
        return action

    def learn(self):
        if len(self.replay_memory) < self.BATCH_SIZE:
            return

        minibatch = random.sample(self.replay_memory, self.BATCH_SIZE)

        current_states = np.array([transition[0] for transition in minibatch])
        current_qs_list = self.model.predict(current_states, verbose=0)

        new_current_states = np.array([transition[3] for transition in minibatch])
        future_qs_list = self.target_model.predict(new_current_states, verbose=0)

        X = []
        y = []

        for index, (current_state, action, reward, new_current_state) in enumerate(minibatch):
            max_future_q = np.max(future_qs_list[index])
            new_q = reward + HyperParameters.discount * max_future_q

            current_qs = current_qs_list[index]
            current_qs[action] = new_q

            X.append(current_state)
            y.append(current_qs)

        self.model.fit(np.array(X), np.array(y), epochs=1, batch_size=DeepQLearningControls.BATCH_SIZE,  verbose=0, shuffle=False)

        self.target_update_counter += 1

        if self.target_update_counter > DeepQLearningControls.UPDATE_LIMIT:
            self.target_model.set_weights(self.model.get_weights())
            self.target_update_counter = 0

    def get_qs(self, state):
        state = [state]
        qs = self.model(np.array(state), training=False)
        return qs[0]

    def calculate_stats(self):
        stats = sum(self.rewards) / len(self.rewards), min(self.rewards), max(self.rewards)
        self.rewards.clear()
        return stats

    def save(self, file):
        self.model.save_weights(f"{self.directory}/{file}{HyperParameters.episode}")

    def load(self, file):
        self.model.load_weights(f"{self.directory}/{file}")
        self.align_target_model()
