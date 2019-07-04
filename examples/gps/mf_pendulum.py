#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Filename: mf_pendulum.py
# @Date: 2019-06-16-18-38
# @Author: Hany Abdulsamad
# @Contact: hany@robot-learning.de


import gym
from trajopt.gps import MFGPS


# pendulum env
env = gym.make('Pendulum-TO-v0')
env._max_episode_steps = 150

alg = MFGPS(env, nb_steps=150,
            kl_bound=25.,
            init_ctl_sigma=1.0,
            activation=range(100, 150))

# run gps
trace = alg.run(nb_episodes=10)

# plot dists
alg.plot()

# execute and plot
nb_episodes = 25
data = alg.sample(nb_episodes, stoch=False)

import matplotlib.pyplot as plt

plt.figure()
for k in range(alg.nb_xdim):
    plt.subplot(alg.nb_xdim + alg.nb_udim, 1, k + 1)
    plt.plot(data['x'][k, ...])

for k in range(alg.nb_udim):
    plt.subplot(alg.nb_xdim + alg.nb_udim, 1, alg.nb_xdim + k + 1)
    plt.plot(data['u'][k, ...])

plt.show()

# plot objective
plt.figure()
plt.plot(trace)
plt.show()
