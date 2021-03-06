import gym
from gym import spaces
from gym.utils import seeding

import autograd.numpy as np
from autograd import jacobian
from autograd.tracer import getval


def wrap_angle(x):
    # wraps angle between [-pi, pi]
    return ((x + np.pi) % (2. * np.pi)) - np.pi


class DoubleCartpole(gym.Env):

    def __init__(self):
        self.dm_state = 6
        self.dm_act = 1

        self.dt = 0.01

        self.sigma = 1e-8 * np.eye(self.dm_state)

        # x = [x, th1, th2, dx, dth1, dth2]
        self.g = np.array([0., 0., 0.,
                           0., 0., 0.])
        self.gw = np.array([1e1, 1e4, 1e4,
                            1e0, 1e0, 1e0])

        self.xmax = np.array([10., np.inf, np.inf,
                              np.inf, np.inf, np.inf])
        self.observation_space = spaces.Box(low=-self.xmax,
                                            high=self.xmax)

        self.slew_rate = False
        self.uw = 1e-5 * np.ones((self.dm_act, ))
        self.umax = 5.0 * np.ones((self.dm_act, ))
        self.action_space = spaces.Box(low=-self.umax,
                                       high=self.umax, shape=(1,))

        self.x0 = np.array([0., np.pi, np.pi,
                            0., 0., 0.])
        self.sigma0 = 1e-4 * np.eye(self.dm_state)

        self.periodic = False

        self.state = None
        self.np_random = None

        self.seed()

    @property
    def xlim(self):
        return self.xmax

    @property
    def ulim(self):
        return self.umax

    def dynamics(self, x, u):
        _u = np.clip(u, -self.ulim, self.ulim)

        # import from: https://github.com/JoeMWatson/input-inference-for-control/
        """
        http://www.lirmm.fr/~chemori/Temp/Wafa/double%20pendule%20inverse.pdf
        """

        # x = [x, th1, th2, dx, dth1, dth2]

        g = 9.81
        Mc = 0.37
        Mp1 = 0.127
        Mp2 = 0.127
        Mt = Mc + Mp1 + Mp2
        L1 = 0.3365
        L2 = 0.3365
        l1 = L1 / 2.
        l2 = L2 / 2.
        J1 = Mp1 * L1 / 12.
        J2 = Mp2 * L2 / 12.

        def f(x, u):

            q = x[0]
            th1 = x[1]
            th2 = x[2]
            dq = x[3]
            dth1 = x[4]
            dth2 = x[5]

            s1 = np.sin(th1)
            c1 = np.cos(th1)
            s2 = np.sin(th2)
            c2 = np.cos(th2)
            sdth = np.sin(th1 - th2)
            cdth = np.cos(th1 - th2)

            # helpers
            l1_mp1_mp2 = Mp1 * l1 + Mp2 * L2
            l1_mp1_mp2_c1 = l1_mp1_mp2 * c1
            Mp2_l2 = Mp2 * l2
            Mp2_l2_c2 = Mp2_l2 * c2
            l1_l2_Mp2 = L1 * l2 * Mp2
            l1_l2_Mp2_cdth = l1_l2_Mp2 * cdth

            # inertia
            M11 = Mt
            M12 = l1_mp1_mp2_c1
            M13 = Mp2_l2_c2
            M21 = l1_mp1_mp2_c1
            M22 = (l1 ** 2) * Mp1 + (L1 ** 2) * Mp2 + J1
            M23 = l1_l2_Mp2_cdth
            M31 = Mp2_l2_c2
            M32 = l1_l2_Mp2_cdth
            M33 = (l2 ** 2) * Mp2 + J2

            # coreolis
            C11 = 0.
            C12 = - l1_mp1_mp2 * dth1 * s1
            C13 = - Mp2_l2 * dth2 * s2
            C21 = 0.
            C22 = 0.
            C23 = l1_l2_Mp2 * dth2 * sdth
            C31 = 0.
            C32 = - l1_l2_Mp2 * dth1 * sdth
            C33 = 0.

            # gravity
            G11 = 0.
            G21 = - (Mp1 * l1 + Mp2 * L1) * g * s1
            G31 = - Mp2 * l2 * g * s2

            # make matrices
            M = np.vstack((np.hstack((M11, M12, M13)), np.hstack((M21, M22, M23)), np.hstack((M31, M32, M33))))
            C = np.vstack((np.hstack((C11, C12, C13)), np.hstack((C21, C22, C23)), np.hstack((C31, C32, C33))))
            G = np.vstack((G11, G21, G31))

            action = np.vstack((u, 0.0, 0.0))

            M_inv = np.linalg.inv(M)
            C_dx = np.dot(C, x[3:].reshape((-1, 1)))
            ddx = np.dot(M_inv, action - C_dx - G).squeeze()

            return np.hstack((dq, dth1, dth2, ddx))

        k1 = f(x, _u)
        k2 = f(x + 0.5 * self.dt * k1, _u)
        k3 = f(x + 0.5 * self.dt * k2, _u)
        k4 = f(x + self.dt * k3, _u)

        xn = x + self.dt / 6. * (k1 + 2. * k2 + 2. * k3 + k4)
        xn = np.clip(xn, -self.xlim, self.xlim)

        return xn

    def features(self, x):
        return x

    def features_jacobian(self, x):
        J = jacobian(self.features, 0)
        j = self.features(x) - J(x) @ x
        return J, j

    def noise(self, x=None, u=None):
        _u = np.clip(u, -self.ulim, self.ulim)
        _x = np.clip(x, -self.xlim, self.xlim)
        return self.sigma

    def cost(self, x, u, u_last, a):
        c = 0.

        if self.slew_rate:
            c += (u - u_last).T @ np.diag(self.uw) @ (u - u_last)
        else:
            c += u.T @ np.diag(self.uw) @ u

        if a:
            y = np.hstack((x[0],
                           wrap_angle(x[1]),
                           wrap_angle(x[2]),
                           x[3], x[4], x[5])) if self.periodic else x
            J, j = self.features_jacobian(getval(y))
            z = J(getval(y)) @ y + j
            c += a * (z - self.g).T @ np.diag(self.gw) @ (z - self.g)

        return c

    def seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def step(self, u):
        # state-action dependent noise
        _sigma = self.noise(self.state, u)
        # evolve deterministic dynamics
        self.state = self.dynamics(self.state, u)
        # add noise
        self.state = self.np_random.multivariate_normal(mean=self.state, cov=_sigma)
        return self.state, [], False, {}

    def init(self):
        return self.x0, self.sigma0

    def reset(self):
        self.state = self.np_random.multivariate_normal(mean=self.x0, cov=self.sigma0)
        return self.state


class DoubleCartpoleWithCartesianCost(DoubleCartpole):

    def __init__(self):
        super(DoubleCartpoleWithCartesianCost, self).__init__()

        # g = [x, cs_th1, sn_th1, cs_th2, sn_th2, dx, dth1, dth2]
        self.g = np.array([0.,
                           1., 0.,
                           1., 0.,
                           0., 0., 0.])

        self.gw = np.array([1e1,
                            1e4, 1e4,
                            1e4, 1e4,
                            1e0, 1e0, 1e0])

    def features(self, x):
        return np.array([x[0],
                         np.cos(x[0]), np.sin(x[0]),
                         np.cos(x[1]), np.sin(x[1]),
                         x[2], x[3], x[4]])
