from __future__ import division, print_function, absolute_import
from sklearn.neighbors import NearestNeighbors


class AbstractNearestNeighborsComputer(object):

    def __call__(self, affinity_mat):
        raise NotImplementedError()


class ScikitNearestNeighbors(AbstractNearestNeighborsComputer):

    def __init__(self, n_neighbors, nn_n_jobs):
        self.n_neighbors = n_neighbors
        self.nn_n_jobs = nn_n_jobs
        self.nn_object = NearestNeighbors( 
                            algorithm="brute", metric="precomputed",
                            n_jobs=self.nn_n_jobs)

    def __call__(self, affinity_mat):
        return self.nn_object.fit(-affinity_mat).kneighbors(
                X=-affinity_mat,
                n_neighbors=min(self.n_neighbors+1,
                                len(affinity_mat)),
                return_distance=False)
