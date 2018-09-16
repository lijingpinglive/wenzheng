#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# ==============================================================================
#          \file   ptr-net.py
#        \author   chenghuige  
#          \date   2018-01-15 11:50:08.306272
#   \Description  
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys 
import os

import tensorflow as tf  
flags = tf.app.flags
FLAGS = flags.FLAGS

from tensorflow import keras

import wenzheng
from wenzheng.utils import vocabulary, embedding

from algos.config import NUM_CLASSES

import melt
    
class Model(keras.Model):
  def __init__(self):
    super(Model, self).__init__()
    vocabulary.init()
    vocab_size = vocabulary.get_vocab_size() 

    ## adadelta adagrad will need cpu, so just use adam..
    #with tf.device('/cpu:0'):
    self.embedding = wenzheng.utils.Embedding(vocab_size, FLAGS.emb_dim, 
                                              FLAGS.word_embedding_file, 
                                              trainable=FLAGS.finetune_word_embedding)
    self.num_layers = FLAGS.num_layers
    self.num_units = FLAGS.rnn_hidden_size
    self.keep_prob = FLAGS.keep_prob

    self.encode = melt.layers.CudnnRnn(num_layers=self.num_layers, num_units=self.num_units, keep_prob=self.keep_prob)

    self.pooling = melt.layers.MaxPooling()
    #self.pooling = keras.layers.GlobalMaxPool1D()

    self.logits = keras.layers.Dense(NUM_CLASSES, activation=None)
    self.logits2 = keras.layers.Dense(NUM_CLASSES, activation=None)

  def call(self, input, training=False):
    x = input['rcontent'] if FLAGS.rcontent else input['content']
    batch_size = melt.get_shape(x, 0)
    length = melt.length(x)
    #with tf.device('/cpu:0'):
    x = self.embedding(x)
    
    num_units = [melt.get_shape(x, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    #print('----------------length', tf.reduce_max(length), inputs.comment.shape)
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    x = self.encode(x, length, mask_fws=mask_fws, mask_bws=mask_bws)
    #x = self.encode(x)
    x = self.pooling(x, length)
    #x = self.pooling(x)

    if FLAGS.use_type:
      x = tf.concat([x, tf.expand_dims(tf.to_float(input['type']), 1)], 1)

    if not FLAGS.split_type:
      x = self.logits(x)
    else:
      x1 = self.logits(x)
      x2 = self.logits2(x)
      x = tf.cond(tf.cast(input['type'] == 0, tf.bool), lambda: (x1 + x2) / 2., lambda: x2)
    
    return x

class Model2(keras.Model):
  """
  same as Model but with bi encode separately for passage and query
  """
  def __init__(self):
    super(Model2, self).__init__()
    vocabulary.init()
    vocab_size = vocabulary.get_vocab_size() 

    ## adadelta adagrad will need cpu, so just use adam..
    #with tf.device('/cpu:0'):
    self.embedding = wenzheng.utils.Embedding(vocab_size, FLAGS.emb_dim, 
                                              FLAGS.word_embedding_file, 
                                              trainable=FLAGS.finetune_word_embedding)
    self.num_layers = FLAGS.num_layers
    self.num_units = FLAGS.rnn_hidden_size
    self.keep_prob = FLAGS.keep_prob

    self.encode = melt.layers.CudnnRnn2(num_layers=self.num_layers, num_units=self.num_units, keep_prob=self.keep_prob)

    self.pooling = melt.layers.MaxPooling2()
    #self.pooling = keras.layers.GlobalMaxPool1D()

    self.logits = keras.layers.Dense(NUM_CLASSES, activation=None)
    self.logits2 = keras.layers.Dense(NUM_CLASSES, activation=None)

  def call(self, input, training=False):
    x1 = input['query']
    x2 = input['passage']
    length1 = melt.length(x1)
    length2 = melt.length(x2)
    #with tf.device('/cpu:0'):
    x1 = self.embedding(x1)
    x2 = self.embedding(x2)
    
    x = x1
    batch_size = melt.get_shape(x1, 0)

    num_units = [melt.get_shape(x, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    #print('----------------length', tf.reduce_max(length), inputs.comment.shape)
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    
    x = self.encode(x1, length1, x2, length2, mask_fws=mask_fws, mask_bws=mask_bws)
    x = self.pooling(x, length1, length2)
    #x = self.pooling(x)

    if FLAGS.use_type:
      x = tf.concat([x, tf.expand_dims(tf.to_float(input['type']), 1)], 1)

    if not FLAGS.split_type:
      x = self.logits(x)
    else:
      x1 = self.logits(x)
      x2 = self.logits2(x)
      x = tf.cond(tf.cast(input['type'] == 0, tf.bool), lambda: (x1 + x2) / 2., lambda: x2)
    
    return x

class QCAttention(keras.Model):
  def __init__(self):
    super(QCAttention, self).__init__()
    vocabulary.init()
    vocab_size = vocabulary.get_vocab_size() 

    self.embedding = wenzheng.utils.Embedding(vocab_size, FLAGS.emb_dim, 
                                              FLAGS.word_embedding_file, 
                                              trainable=FLAGS.finetune_word_embedding)
    self.num_layers = FLAGS.num_layers
    self.num_units = FLAGS.rnn_hidden_size
    self.keep_prob = FLAGS.keep_prob

    self.encode = melt.layers.CudnnRnn(num_layers=self.num_layers, num_units=self.num_units, keep_prob=self.keep_prob)

    self.att_encode = melt.layers.CudnnRnn(num_layers=1, num_units=self.num_units, keep_prob=self.keep_prob)


    self.att_dot_attention = melt.layers.DotAttention(hidden=self.num_units, keep_prob=self.keep_prob, combiner=FLAGS.att_combiner)
    self.pooling = melt.layers.MaxPooling()

    self.logits = keras.layers.Dense(NUM_CLASSES, activation=None)
    self.logits2 = keras.layers.Dense(NUM_CLASSES, activation=None)

  def call(self, input, training=False):
    q = input['query']
    c = input['passage']
    q_len = melt.length(q)
    c_len = melt.length(c)
    q_mask = tf.cast(q, tf.bool)
    q_emb = self.embedding(q)
    c_emb = self.embedding(c)
    
    x = c_emb
    batch_size = melt.get_shape(x, 0)

    num_units = [melt.get_shape(x, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    
    c = self.encode(c_emb, c_len, mask_fws=mask_fws, mask_bws=mask_bws)
    q = self.encode(q_emb, q_len, mask_fws=mask_fws, mask_bws=mask_bws)

    qc_att = self.att_dot_attention(c, q, mask=q_mask, training=training)

    num_units = [melt.get_shape(qc_att, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    x = self.att_encode(qc_att, c_len, mask_fws=mask_fws, mask_bws=mask_bws)

    x = self.pooling(x, c_len)

    if FLAGS.use_type:
      x = tf.concat([x, tf.expand_dims(tf.to_float(input['type']), 1)], 1)

    if not FLAGS.split_type:
      x = self.logits(x)
    else:
      x1 = self.logits(x)
      x2 = self.logits2(x)
      x = tf.cond(tf.cast(input['type'] == 0, tf.bool), lambda: (x1 + x2) / 2., lambda: x2)
    
    return x

class Rnet(keras.Model):
  def __init__(self):
    super(Rnet, self).__init__()
    vocabulary.init()
    vocab_size = vocabulary.get_vocab_size() 

    self.embedding = wenzheng.utils.Embedding(vocab_size, FLAGS.emb_dim, 
                                              FLAGS.word_embedding_file, 
                                              trainable=FLAGS.finetune_word_embedding)
    self.num_layers = FLAGS.num_layers
    self.num_units = FLAGS.rnn_hidden_size
    self.keep_prob = FLAGS.keep_prob

    self.encode = melt.layers.CudnnRnn(num_layers=self.num_layers, num_units=self.num_units, keep_prob=self.keep_prob)

    # TODO seems not work like layers.Dense... name in graph mode in eager mode will name as att_encode, match_encode 
    # in graph mode just cudnn_rnn, cudnn_rnn_1 so all ignore name=.. not like layers.Dense.. TODO
    self.att_encode = melt.layers.CudnnRnn(num_layers=1, num_units=self.num_units, keep_prob=self.keep_prob)

    self.match_encode = melt.layers.CudnnRnn(num_layers=1, num_units=self.num_units, keep_prob=self.keep_prob)

    # seems share att and match attention is fine a bit improve ? but just follow squad to use diffent dot attention 
    self.att_dot_attention = melt.layers.DotAttention(hidden=self.num_units, keep_prob=self.keep_prob, combiner=FLAGS.att_combiner)
    self.match_dot_attention = melt.layers.DotAttention(hidden=self.num_units, keep_prob=self.keep_prob, combiner=FLAGS.att_combiner)

    self.pooling = melt.layers.MaxPooling()

    self.logits = keras.layers.Dense(NUM_CLASSES, activation=None)
    self.logits2 = keras.layers.Dense(NUM_CLASSES, activation=None)

  def call(self, input, training=False):
    q = input['query']
    c = input['passage']
    q_len = melt.length(q)
    c_len = melt.length(c)
    q_mask = tf.cast(q, tf.bool)
    c_mask = tf.cast(c, tf.bool)
    q_emb = self.embedding(q)
    c_emb = self.embedding(c)
    
    x = c_emb
    batch_size = melt.get_shape(x, 0)

    num_units = [melt.get_shape(x, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(self.num_layers)]
    
    c = self.encode(c_emb, c_len, mask_fws=mask_fws, mask_bws=mask_bws)
    q = self.encode(q_emb, q_len, mask_fws=mask_fws, mask_bws=mask_bws)

    qc_att = self.att_dot_attention(c, q, mask=q_mask, training=training)

    num_units = [melt.get_shape(qc_att, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    att = self.att_encode(qc_att, c_len, mask_fws=mask_fws, mask_bws=mask_bws)

    self_att = self.match_dot_attention(att, att, mask=c_mask, training=training)

    num_units = [melt.get_shape(self_att, -1) if layer == 0 else 2 * self.num_units for layer in range(self.num_layers)]
    mask_fws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    mask_bws = [melt.dropout(tf.ones([batch_size, 1, num_units[layer]], dtype=tf.float32), keep_prob=self.keep_prob, training=training, mode=None) for layer in range(1)]
    x = self.match_encode(self_att, c_len, mask_fws=mask_fws, mask_bws=mask_bws)

    x = self.pooling(x, c_len)

    if FLAGS.use_type:
      x = tf.concat([x, tf.expand_dims(tf.to_float(input['type']), 1)], 1)

    if not FLAGS.split_type:
      x = self.logits(x)
    else:
      x1 = self.logits(x)
      x2 = self.logits2(x)
      #x = tf.cond(tf.cast(input['type'] == 0, tf.bool), lambda: (x1 + x2) / 2., lambda: x2)
      x = tf.cond(tf.cast(input['type'] == 0, tf.bool), lambda: x1, lambda: x2)
    
    return x

def criterion(model, x, y, training=False):
  y_ = model(x, training=training)
  return tf.losses.sparse_softmax_cross_entropy(logits=y_, labels=y) 