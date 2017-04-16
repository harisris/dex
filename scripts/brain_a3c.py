# By Nick Erickson
# A3C Brain

# Deep Learning Modules
from keras import backend as K
from keras.models import Model, Input
from keras.models import model_from_json
from keras.layers.core import Dense
from keras.optimizers import SGD , Adam , RMSprop

import tensorflow as tf
from models import default_model

from memory import Memory_v2
import numpy as np
import data_aug

MEMORY_SIZE = 150000

# Class concept from Jaromir Janisch, 2017
# https://jaromiru.com/2017/03/26/lets-make-an-a3c-implementation/
class Brain:
    train_queue = [ [], [], [], [], [] ]    # s, a, r, s', s' terminal mask

    def __init__(self, state_dim, action_dim, hyper, modelFunc=None):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = hyper.gamma
        self.n_step_return = hyper.memory_size
        self.gamma_n = self.gamma ** self.n_step_return
        self.loss_v = hyper.extra.loss_v
        self.loss_entropy = hyper.extra.loss_entropy
        self.batch = hyper.batch
        self.max_size = self.batch * 10
        self.learning_rate = hyper.learning_rate
        
        self.NONE_STATE = np.zeros(state_dim)
        self.session = tf.Session()
        K.set_session(self.session)
        K.manual_variable_initialization(True)

        self.model = self.create_model(modelFunc)
        self.graph = self.create_graph(self.model)

        self.session.run(tf.global_variables_initializer())
        self.default_graph = tf.get_default_graph()

        self.cur_size = 0
        self.s = np.zeros([self.max_size] + state_dim)
        self.a = np.zeros([self.max_size] + [self.action_dim])
        self.r = np.zeros((self.max_size, 1))
        self.s_ = np.zeros([self.max_size] + state_dim)
        self.s_mask = np.zeros((self.max_size, 1))
        
        self.brain_memory = Memory_v2(MEMORY_SIZE, self.state_dim, self.action_dim)
        
        
        #self.default_graph.finalize()    # avoid modifications

    def create_model(self, modelFunc=None):
        print(self.state_dim)
        print(self.action_dim)
        if modelFunc:
            model = modelFunc(self.state_dim, self.action_dim)
        else:
            l_input = Input( batch_shape=(None, self.state_dim[0]) )
            l_dense = Dense(16, activation='relu')(l_input)
    
            out_actions = Dense(self.action_dim, activation='softmax')(l_dense)
            out_value   = Dense(1, activation='linear')(l_dense)
    
            model = Model(inputs=[l_input], outputs=[out_actions, out_value])
        model._make_predict_function() # have to initialize before threading
        print("Finished building the model")
        print(model.summary())
        return model
        
    def create_graph(self, model):
        #print(self.state_dim)
        #print(self.state_dim[0])
        zzz = [None] + self.state_dim
        print(zzz)
        s_t = tf.placeholder(tf.float32, shape=(zzz))
        a_t = tf.placeholder(tf.float32, shape=(None, self.action_dim))
        r_t = tf.placeholder(tf.float32, shape=(None, 1)) # not immediate, but discounted n step reward
        
        p, v = model(s_t)

        log_prob = tf.log( tf.reduce_sum(p * a_t, axis=1, keep_dims=True) + 1e-10)
        advantage = r_t - v

        loss_policy = - log_prob * tf.stop_gradient(advantage)                                    # maximize policy
        loss_value  = self.loss_v * tf.square(advantage)                                                # minimize value error
        entropy = self.loss_entropy * tf.reduce_sum(p * tf.log(p + 1e-10), axis=1, keep_dims=True)    # maximize entropy (regularization)

        loss_total = tf.reduce_mean(loss_policy + loss_value + entropy)

        optimizer = tf.train.RMSPropOptimizer(self.learning_rate, decay=.99) # Previously .99
        minimize = optimizer.minimize(loss_total)

        return s_t, a_t, r_t, minimize

    def optimize_v2(self):
        #print('hey')
        if self.brain_memory.isFull != True:
            return
        idx = self.brain_memory.sample(self.batch)
        
        s  = self.brain_memory.s [idx, :]
        a  = self.brain_memory.a [idx, :]
        r  = np.copy(self.brain_memory.r [idx, :])
        s_ = self.brain_memory.s_[idx, :]
        t  = self.brain_memory.t [idx, :]
        
        v  = self.predict_v(s_)
        
        r = r + self.gamma_n * v * t # set v to 0 where s_ is terminal state
        
        s_t, a_t, r_t, minimize = self.graph

        self.session.run(minimize, feed_dict={s_t: s, a_t: a, r_t: r})    
        self.cur_size = 0
        
    def optimize(self):
        if self.cur_size < self.batch:
            return

        v = self.predict_v(self.s_[:self.cur_size])
        #v = v.reshape(self.cur_size)
        #print(v.shape)
        #print(self.s_mask[:self.cur_size].shape)
        #print((self.gamma_n * v.T * self.s_mask[:self.cur_size]).reshape(self.cur_size).shape)
        r = self.r[:self.cur_size] + self.gamma_n * v * self.s_mask[:self.cur_size]    # set v to 0 where s_ is terminal state
        
        s_t, a_t, r_t, minimize = self.graph

        
        
        #s = self.s[:self.cur_size]
        #a = self.a[:self.cur_size]
        #print(s.shape)
        #print(a.shape)
        #print(r.shape)
        self.session.run(minimize, feed_dict={s_t: self.s[:self.cur_size], a_t: self.a[:self.cur_size], r_t: r})    
        self.cur_size = 0
        
    def optimizeOld(self):
        if len(self.train_queue[0]) < self.batch:
            return
        s, a, r, s_, s_mask = self.train_queue
        self.train_queue = [ [], [], [], [], [] ]

        a_cats = []
        for a_ in a:
            a_cat = np.zeros(self.action_dim)
            a_cat[a_] = 1
            a_cats.append(a_cat)
        #print(np.array(s[0]).shape)
        #print(np.array(s).shape)
        #s = np.vstack(s)
        
        s = np.array(s)
        s_ = np.array(s_)
        a = np.vstack(a_cats)
        r = np.vstack(r)
        #s_ = np.vstack(s_)
        s_mask = np.vstack(s_mask)

        v = self.predict_v(s_)
        r = r + self.gamma_n * v * s_mask    # set v to 0 where s_ is terminal state
        
        s_t, a_t, r_t, minimize = self.graph

        self.session.run(minimize, feed_dict={s_t: s, a_t: a, r_t: r})

    def train_augmented(self, s, a, r, s_):
        
        if s_ is None:
            self.train_push_all_augmented_v2(data_aug.full_augment([[s, a, r, self.NONE_STATE, 0.]]))
        else:    
            self.train_push_all_augmented_v2(data_aug.full_augment([[s, a, r, s_, 1.]]))
        
        
    def train_push_all_augmented(self, frames):
        for frame in frames:
            self.train_push_augmented(frame)
        self.optimize()
        
    def train_push_augmented(self, frame):
        self.s[self.cur_size] = frame[0]

        a_cat = np.zeros(self.action_dim)
        a_cat[frame[1]] = 1

        self.a[self.cur_size] = a_cat
        self.r[self.cur_size] = frame[2]
        self.s_[self.cur_size] = frame[3]
        self.s_mask[self.cur_size] = frame[4]


        self.cur_size += 1
        
    def train_push_augmented_old(self, frame):
        self.train_queue[0].append(frame[0])
        self.train_queue[1].append(frame[1])
        self.train_queue[2].append(frame[2])  
        self.train_queue[3].append(frame[3])
        self.train_queue[4].append(frame[4])
        
    def train_push_all_augmented_v2(self, frames):
        for frame in frames:
            self.train_push_augmented_v2(frame)

    def train_push_augmented_v2(self, frame):
        #self.s[self.cur_size] = frame[0]

        a_cat = np.zeros(self.action_dim)
        a_cat[frame[1]] = 1

        #self.a[self.cur_size] = a_cat
        #self.r[self.cur_size] = frame[2]
        #self.s_[self.cur_size] = frame[3]
        #self.s_mask[self.cur_size] = frame[4]

        self.brain_memory.add_single(frame[0], a_cat, frame[2], frame[3], frame[4])

        #self.cur_size += 1        
            
    """
    def train_push(self, s, a, r, s_):
        self.train_queue[0].append(s)
        self.train_queue[1].append(a)
        self.train_queue[2].append(r)
        if s_ is None:
            self.train_queue[3].append(self.NONE_STATE)
            self.train_queue[4].append(0.)
        else:    
            self.train_queue[3].append(s_)
            self.train_queue[4].append(1.)

        self.optimize()
    """
       
    def predict(self, s):
        with self.default_graph.as_default():
            p, v = self.model.predict(s)
            return p, v

    def predict_p(self, s):
        with self.default_graph.as_default():
            p, v = self.model.predict(s)        
            return p

    def predict_v(self, s):
        with self.default_graph.as_default():
            p, v = self.model.predict(s)
            return v