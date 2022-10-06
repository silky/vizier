# Copyright 2022 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for eagle_optimizer."""

import logging
import math
from typing import Callable, Union

import numpy as np
from vizier import pyvizier as vz
from vizier._src.algorithms.optimizers import eagle_strategy
from vizier._src.algorithms.optimizers import vectorized_base

from absl.testing import absltest
from absl.testing import parameterized


# TODO: find a better place for the statistical test.
def compute_p_value(n_features: int, evaluations: int,
                    best_features: np.ndarray, center: Union[np.ndarray,
                                                             float]) -> float:
  """P-value assuming random search as null hypothesis.

  Computes the probability of achieving 'best_features' by running random search
  'evaluations' times. The assumption is that the search space is [-1,1]^n.

  It computes the volume of a ball with radius induced by the distance between
  'best_features' and 'center', and divide it by the volume of hypercube. It
  then computes the probability of at least one of the evaluations achieving
  that distance.

  Arguments:
    n_features:
    evaluations:
    best_features:
    center:

  Returns:
    The p-value.
  """

  def ball_volume(n, r):
    return math.pi**(n / 2) / math.gamma(n / 2 + 1) * r**n

  # Compute the radius associated with the error.
  squared_dist = np.sum(np.square(best_features - center), axis=-1)
  logging.info('Squared dist from center: %s', squared_dist)
  radius = np.sqrt(squared_dist)
  logging.info('Radius: %s', radius)
  # The probability of randomly achieving squared error.
  p = ball_volume(n_features, radius) / 2**n_features
  logging.info('Probability of a single "within": %s', p)
  if p >= 1:
    return 1
  # The probability that at least one of the evalutaions is in the ball.
  return 1 - (1 - p)**evaluations


def sphere_objective_factory(
    shift: Union[np.ndarray, float]) -> Callable[[np.ndarray], float]:
  return lambda x: -np.sum(np.square(x - shift), axis=-1)


def create_problem(n_features: int, low_bound: float,
                   high_bound: float) -> vz.ProblemStatement:
  problem = vz.ProblemStatement()
  root = problem.search_space.select_root()
  for i in range(n_features):
    root.add_float_param('x%d' % i, low_bound, high_bound)
  return problem


class EagleOptimizerConvegenceTest(parameterized.TestCase):
  """Test for optimizing acquisition functions using vectorized Eagle Strategy."""

  # TODO: Add BBOB functions once they can support 2D arrays.
  # TODO: Add or replace with efficiency-curve convergence test.
  @parameterized.parameters(list(range(10, 21)))
  def test_converges(self, n_features):
    logging.info('==== New Convergence Test (n_features: %s) ====', n_features)
    pool_size = 50
    batch_size = 10
    low_bound = -1.0
    high_bound = 1.0
    evaluations = 20_000
    total_check = 1
    threshold_checks = 1
    alpha = 0.05

    success_count = 0
    for _ in range(total_check):
      shift = np.random.uniform(
          low_bound * 0.8, high_bound * 0.8, size=(n_features,))
      # Create eagle factory
      eagle_factory = eagle_strategy.VectorizedEagleStrategyFactory(
          eagle_config=eagle_strategy.EagleStrategyConfig(),
          pool_size=pool_size,
          batch_size=batch_size,
          low_bound=low_bound,
          high_bound=high_bound,
      )
      # Create the optimizer.
      optimizer = vectorized_base.VectorizedOptimizer(
          strategy_factory=eagle_factory, max_evaluations=evaluations)
      # Simluate a problem.
      problem = create_problem(n_features, low_bound, high_bound)
      # Optimize.
      optimizer.optimize(problem, sphere_objective_factory(shift))
      # Get best results.
      best_parameters = optimizer.best_results[0]
      best_reward = optimizer.best_results[1]
      p_value = compute_p_value(n_features, evaluations, best_parameters, shift)
      logging.info('Number of features: %s', n_features)
      logging.info('Shift: %s', shift)
      logging.info('Best parameters: %s', best_parameters)
      logging.info('Best reward: %s', best_reward)
      logging.info('P value: %s', p_value)
      logging.info('Alpha: %s', alpha)
      if p_value <= alpha:
        success_count += 1
    logging.info('Success checks: %s / %s.', success_count, total_check)
    logging.info('Optimizer details:\n%s', optimizer)
    self.assertGreaterEqual(success_count, threshold_checks)


if __name__ == '__main__':
  absltest.main()