#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calculation of RDMs from datasets
@author: heiko, benjamin
"""

from collections.abc import Iterable
from copy import deepcopy
import numpy as np
from scipy.special import comb
from pyrsa.rdm.rdms import RDMs
from pyrsa.rdm.rdms import concat
from pyrsa.data import average_dataset_by
from pyrsa.util.matrix import pairwise_contrast_sparse


def calc_rdm(dataset, method='euclidean', descriptor=None, noise=None,
             cv_descriptor=None, prior_lambda=1, prior_weight=0.1):
    """
    calculates an RDM from an input dataset

    Args:
        dataset (pyrsa.data.dataset.DatasetBase):
            The dataset the RDM is computed from
        method (String):
            a description of the dissimilarity measure (e.g. 'Euclidean')
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
        noise (numpy.ndarray):
            dataset.n_channel x dataset.n_channel
            precision matrix used to calculate the RDM
            used only for Mahalanobis and Crossnobis estimators
            defaults to an identity matrix, i.e. euclidean distance

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    if isinstance(dataset, Iterable):
        rdms = []
        for i_dat in range(len(dataset)):
            if noise is None:
                rdms.append(calc_rdm(
                    dataset[i_dat], method=method,
                    descriptor=descriptor,
                    cv_descriptor=cv_descriptor,
                    prior_lambda=prior_lambda, prior_weight=prior_weight))
            elif isinstance(noise, np.ndarray) and noise.ndim == 2:
                rdms.append(calc_rdm(
                    dataset[i_dat], method=method,
                    descriptor=descriptor,
                    noise=noise,
                    cv_descriptor=cv_descriptor,
                    prior_lambda=prior_lambda, prior_weight=prior_weight))
            elif isinstance(noise, Iterable):
                rdms.append(calc_rdm(
                    dataset[i_dat], method=method,
                    descriptor=descriptor,
                    noise=noise[i_dat],
                    cv_descriptor=cv_descriptor,
                    prior_lambda=prior_lambda, prior_weight=prior_weight))
        rdm = concat(rdms)
    else:
        if method == 'euclidean':
            rdm = calc_rdm_euclid(dataset, descriptor)
        elif method == 'correlation':
            rdm = calc_rdm_correlation(dataset, descriptor)
        elif method == 'correlation_cv':
            rdm = calc_rdm_correlation_cv(dataset, descriptor)
        elif method == 'mahalanobis':
            rdm = calc_rdm_mahalanobis(dataset, descriptor, noise)
        elif method == 'crossnobis':
            rdm = calc_rdm_crossnobis(dataset, descriptor, noise,
                                      cv_descriptor)
        elif method == 'crosseuclid':
            rdm = calc_rdm_crossnobis(dataset, descriptor, None,
                                      cv_descriptor)
        elif method == 'poisson':
            rdm = calc_rdm_poisson(dataset, descriptor,
                                   prior_lambda=prior_lambda,
                                   prior_weight=prior_weight)
        elif method == 'poisson_cv':
            rdm = calc_rdm_poisson_cv(dataset, descriptor,
                                      cv_descriptor=cv_descriptor,
                                      prior_lambda=prior_lambda,
                                      prior_weight=prior_weight)
        else:
            raise(NotImplementedError)
    return rdm


def calc_rdm_movie(dataset, method='euclidean', descriptor=None, noise=None,
             cv_descriptor=None, prior_lambda=1, prior_weight=0.1,
             time_descriptor='time', bins=None):
    """
    calculates an RDM movie from an input TemporalDataset

    Args:
        dataset (pyrsa.data.dataset.TemporalDataset):
            The dataset the RDM is computed from
        method (String):
            a description of the dissimilarity measure (e.g. 'Euclidean')
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
        noise (numpy.ndarray):
            dataset.n_channel x dataset.n_channel
            precision matrix used to calculate the RDM
            used only for Mahalanobis and Crossnobis estimators
            defaults to an identity matrix, i.e. euclidean distance
        time_descriptor (String): descriptor key that points to the time dimension in
            dataset.time_descriptors. Defaults to 'time'.
        bins (array-like): list of bins, with bins[i] containing the vector
            of time-points for the i-th bin. Defaults to no binning.

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with RDM movie
    """

    if isinstance(dataset, Iterable):
        rdms = []
        for i_dat, _ in enumerate(dataset):
            if noise is None:
                rdms.append(calc_rdm_movie(
                    dataset[i_dat], method=method,
                    descriptor=descriptor))
            elif isinstance(noise, np.ndarray) and noise.ndim == 2:
                rdms.append(calc_rdm_movie(
                    dataset[i_dat], method=method,
                    descriptor=descriptor,
                    noise=noise))
            elif isinstance(noise, Iterable):
                rdms.append(calc_rdm_movie(
                    dataset[i_dat], method=method,
                    descriptor=descriptor,
                    noise=noise[i_dat]))
        rdm = concat(rdms)
    else:
        if bins is not None:
            binned_data = dataset.bin_time(time_descriptor, bins)
            splited_data = binned_data.split_time(time_descriptor)
            time = binned_data.time_descriptors[time_descriptor]
        else:
            splited_data = dataset.split_time(time_descriptor)
            time = dataset.time_descriptors[time_descriptor]

        rdms = []
        for dat in splited_data:
            dat_single = dat.convert_to_dataset(time_descriptor)
            rdms.append(calc_rdm(dat_single, method=method,
                                 descriptor=descriptor, noise=noise,
                                 cv_descriptor=cv_descriptor,
                                 prior_lambda=prior_lambda,
                                 prior_weight=prior_weight))

        rdm = concat(rdms)
        rdm.rdm_descriptors[time_descriptor] = time
    return rdm


def calc_rdm_euclid(dataset, descriptor=None):
    """
    calculates an RDM from an input dataset using euclidean distance
    If multiple instances of the same condition are found in the dataset
    they are averaged.

    Args:
        dataset (pyrsa.data.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    measurements, desc, descriptor = _parse_input(dataset, descriptor)
    diff = _calc_pairwise_differences(measurements)
    rdm = np.einsum('ij,ij->i', diff, diff) / measurements.shape[1]
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='euclidean',
               rdm_descriptors=deepcopy(dataset.descriptors))
    rdm.pattern_descriptors[descriptor] = desc
    return rdm


def calc_rdm_correlation(dataset, descriptor=None):
    """
    calculates an RDM from an input dataset using correlation distance
    If multiple instances of the same condition are found in the dataset
    they are averaged.

    Args:
        dataset (pyrsa.data.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    ma, desc, descriptor = _parse_input(dataset, descriptor)
    ma = ma - ma.mean(axis=1, keepdims=True)
    ma /= np.sqrt(np.einsum('ij,ij->i', ma, ma))[:, None]
    rdm = 1 - np.einsum('ik,jk', ma, ma)
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='correlation',
               rdm_descriptors=deepcopy(dataset.descriptors))
    rdm.pattern_descriptors[descriptor] = desc
    return rdm


def calc_rdm_correlation_cv(dataset, descriptor=None):
    """
    Calculates an RDM from an input dataset using a cross-validated correlation
    distance, based on https://github.com/fwillett/cvVectorStats

    Performs leave-one-out crossvalidation. May be extended to split along a
    cv_descriptor in the future.

    Args:
        dataset (pyrsa.data.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    # Average dataset by descriptor
    measurement_avgs, desc, descriptor = _parse_input(dataset, descriptor)
    # dataset.sort_by(descriptor) ## Is this necessary?

    # 1. Calculate crossvalidated magnitude of each class
    cv_magnitude_centered = []
    for d in desc:
        data_subset = dataset.subset_obs(descriptor, d)
        cv_magnitude_centered.append(
            _calc_magnitude_cv(data_subset.measurements, subtract_mean=True)
        )

    # 2. Pre-subtract mean along channel axis
    # to match correlation equation
    measurement_avgs_centered = (measurement_avgs -
            measurement_avgs.mean(axis=-1, keepdims=True))

    # 3. Estimate correlation
    n_cond = len(desc)
    rdm = np.empty(comb(n_cond, 2, exact=True))
    k = 0
    for i_cond in range(n_cond - 1):
        for j_cond in range(i_cond + 1, n_cond):
            # Use the normal equation for correlation, except use a
            # crossvalidated estimate of the magnitudes
            corr_numerator = np.dot(
                    measurement_avgs_centered[i_cond],
                    measurement_avgs_centered[j_cond])
            corr_denominator = (cv_magnitude_centered[i_cond] *
                    cv_magnitude_centered[j_cond])
            rdm[k] = 1 - (corr_numerator / corr_denominator)

            k += 1

    # 4. Package in an RDM object
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='correlation_cv',
               descriptors=dataset.descriptors)
    rdm.pattern_descriptors[descriptor] = desc
    return rdm


def calc_rdm_mahalanobis(dataset, descriptor=None, noise=None):
    """
    calculates an RDM from an input dataset using mahalanobis distance
    If multiple instances of the same condition are found in the dataset
    they are averaged.

    Args:
        dataset (pyrsa.data.dataset.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset
        noise (numpy.ndarray):
            dataset.n_channel x dataset.n_channel
            precision matrix used to calculate the RDM
            default: identity matrix, i.e. euclidean distance

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    if noise is None:
        rdm = calc_rdm_euclid(dataset, descriptor)
    else:
        measurements, desc, descriptor = _parse_input(dataset, descriptor)
        noise = _check_noise(noise, dataset.n_channel)
        # calculate difference @ precision @ difference for all pairs
        # first calculate the difference vectors diff and precision @ diff
        # then calculate the inner product
        diff = _calc_pairwise_differences(measurements)
        diff2 = (noise @ diff.T).T
        rdm = np.einsum('ij,ij->i', diff, diff2) / measurements.shape[1]
        rdm = RDMs(dissimilarities=np.array([rdm]),
                   dissimilarity_measure='Mahalanobis',
                   rdm_descriptors=deepcopy(dataset.descriptors))
        rdm.pattern_descriptors[descriptor] = desc
        rdm.descriptors['noise'] = noise
    return rdm


def calc_rdm_crossnobis(dataset, descriptor, noise=None,
                        cv_descriptor=None):
    """
    calculates an RDM from an input dataset using Cross-nobis distance
    This performs leave one out crossvalidation over the cv_descriptor.

    As the minimum input provide a dataset and a descriptor-name to
    define the rows & columns of the RDM.
    You may pass a noise precision. If you don't an identity is assumed.
    Also a cv_descriptor can be passed to define the crossvalidation folds.
    It is recommended to do this, to assure correct calculations. If you do
    not, this function infers a split in order of the dataset, which is
    guaranteed to fail if there are any unbalances.

    This function also accepts a list of noise precision matricies.
    It is then assumed that this is the precision of the mean from
    the corresponding crossvalidation fold, i.e. if multiple measurements
    enter a fold, please compute the resulting noise precision in advance!

    To assert equal ordering in the folds the dataset is initially sorted
    according to the descriptor used to define the patterns.

    Args:
        dataset (pyrsa.data.dataset.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset
        noise (numpy.ndarray):
            dataset.n_channel x dataset.n_channel
            precision matrix used to calculate the RDM
            default: identity matrix, i.e. euclidean distance
        cv_descriptor (String):
            obs_descriptor which determines the cross-validation folds

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    noise = _check_noise(noise, dataset.n_channel)
    if descriptor is None:
        raise ValueError('descriptor must be a string! Crossvalidation' +
                         'requires multiple measurements to be grouped')
    if cv_descriptor is None:
        cv_desc = _gen_default_cv_descriptor(dataset, descriptor)
        dataset.obs_descriptors['cv_desc'] = cv_desc
        cv_descriptor = 'cv_desc'
    dataset.sort_by(descriptor)
    cv_folds = np.unique(np.array(dataset.obs_descriptors[cv_descriptor]))
    rdms = []
    if (noise is None) or (isinstance(noise, np.ndarray) and noise.ndim == 2):
        for i_fold in range(len(cv_folds)):
            fold = cv_folds[i_fold]
            data_test = dataset.subset_obs(cv_descriptor, fold)
            data_train = dataset.subset_obs(cv_descriptor,
                                            np.setdiff1d(cv_folds, fold))
            measurements_train, _, _ = \
                average_dataset_by(data_train, descriptor)
            measurements_test, _, _ = \
                average_dataset_by(data_test, descriptor)
            n_cond = measurements_train.shape[0]
            n_channel = measurements_train.shape[1]
            rdm = np.empty(int(n_cond * (n_cond-1) / 2))
            k = 0
            for i_cond in range(n_cond - 1):
                for j_cond in range(i_cond + 1, n_cond):
                    diff_train = measurements_train[i_cond] \
                        - measurements_train[j_cond]
                    diff_test = measurements_test[i_cond] \
                        - measurements_test[j_cond]
                    if noise is None:
                        rdm[k] = np.mean(diff_train * diff_test)
                    else:
                        rdm[k] = np.mean(diff_train
                                         * np.matmul(noise, diff_test))
                    k += 1
            rdms.append(rdm)
    else:  # a list of noises was provided
        measurements = []
        variances = []
        for i_fold in range(len(cv_folds)):
            data = dataset.subset_obs(cv_descriptor, cv_folds[i_fold])
            measurements.append(average_dataset_by(data, descriptor)[0])
            variances.append(np.linalg.inv(noise[i_fold]))
        for i_fold in range(len(cv_folds)):
            for j_fold in range(i_fold + 1, len(cv_folds)):
                if i_fold != j_fold:
                    rdm = _calc_rdm_crossnobis_single(
                        measurements[i_fold], measurements[j_fold],
                        np.linalg.inv(variances[i_fold]
                                      + variances[j_fold]))
                    rdms.append(rdm)
    rdms = np.array(rdms)
    rdm = rdms.mean(axis=0)
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='crossnobis',
               rdm_descriptors=deepcopy(dataset.descriptors))
    _, desc, _ = average_dataset_by(dataset, descriptor)
    rdm.pattern_descriptors[descriptor] = desc
    rdm.descriptors['noise'] = noise
    rdm.descriptors['cv_descriptor'] = cv_descriptor
    return rdm


def calc_rdm_poisson(dataset, descriptor=None, prior_lambda=1,
                     prior_weight=0.1):
    """
    calculates an RDM from an input dataset using the symmetrized
    KL-divergence assuming a poisson distribution.
    If multiple instances of the same condition are found in the dataset
    they are averaged.

    Args:
        dataset (pyrsa.data.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    measurements, desc, descriptor = _parse_input(dataset, descriptor)
    measurements = (measurements + prior_lambda * prior_weight) \
        / (1 + prior_weight)
    diff = _calc_pairwise_differences(measurements)
    diff_log = _calc_pairwise_differences(np.log(measurements))
    rdm = np.einsum('ij,ij->i', diff, diff_log) / measurements.shape[1]
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='poisson',
               rdm_descriptors=deepcopy(dataset.descriptors))
    rdm.pattern_descriptors[descriptor] = desc
    return rdm


def calc_rdm_poisson_cv(dataset, descriptor=None, prior_lambda=1,
                        prior_weight=0.1, cv_descriptor=None):
    """
    calculates an RDM from an input dataset using the crossvalidated
    symmetrized KL-divergence assuming a poisson distribution

    To assert equal ordering in the folds the dataset is initially sorted
    according to the descriptor used to define the patterns.

    Args:
        dataset (pyrsa.data.DatasetBase):
            The dataset the RDM is computed from
        descriptor (String):
            obs_descriptor used to define the rows/columns of the RDM
            defaults to one row/column per row in the dataset
        cv_descriptor (str): The descriptor that indicates the folds
            to use for crossvalidation

    Returns:
        pyrsa.rdm.rdms.RDMs: RDMs object with the one RDM

    """
    if descriptor is None:
        raise ValueError('descriptor must be a string! Crossvalidation' +
                         'requires multiple measurements to be grouped')
    if cv_descriptor is None:
        cv_desc = _gen_default_cv_descriptor(dataset, descriptor)
        dataset.obs_descriptors['cv_desc'] = cv_desc
        cv_descriptor = 'cv_desc'

    dataset.sort_by(descriptor)
    cv_folds = np.unique(np.array(dataset.obs_descriptors[cv_descriptor]))
    for i_fold in range(len(cv_folds)):
        fold = cv_folds[i_fold]
        data_test = dataset.subset_obs(cv_descriptor, fold)
        data_train = dataset.subset_obs(cv_descriptor,
                                        np.setdiff1d(cv_folds, fold))
        measurements_train, _, _ = average_dataset_by(data_train, descriptor)
        measurements_test, _, _ = average_dataset_by(data_test, descriptor)
        measurements_train = (measurements_train
                              + prior_lambda * prior_weight) \
            / (1 + prior_weight)
        measurements_test = (measurements_test
                             + prior_lambda * prior_weight) \
            / (1 + prior_weight)
        diff = _calc_pairwise_differences(measurements_train)
        diff_log = _calc_pairwise_differences(np.log(measurements_test))
        rdm = np.einsum('ij,ij->i', diff, diff_log) \
            / measurements_train.shape[1]
    rdm = RDMs(dissimilarities=np.array([rdm]),
               dissimilarity_measure='poisson_cv',
               rdm_descriptors=deepcopy(dataset.descriptors))
    _, desc, _ = average_dataset_by(dataset, descriptor)
    rdm.pattern_descriptors[descriptor] = desc
    return rdm


def _calc_rdm_crossnobis_single_sparse(measurements1, measurements2, noise):
    c_matrix = pairwise_contrast_sparse(np.arange(measurements1.shape[0]))
    diff_1 = c_matrix @ measurements1
    diff_2 = c_matrix @ measurements2
    diff_2 = noise @ diff_2.transpose()
    rdm = np.einsum('kj,jk->k', diff_1, diff_2) / measurements1.shape[1]
    return rdm


def _calc_rdm_crossnobis_single(measurements1, measurements2, noise):
    diff_1 = _calc_pairwise_differences(measurements1)
    diff_2 = _calc_pairwise_differences(measurements2)
    diff_2 = noise @ diff_2.transpose()
    rdm = np.einsum('kj,jk->k', diff_1, diff_2) / measurements1.shape[1]
    return rdm


def _calc_magnitude_cv(measurements, subtract_mean=False):
    """Assuming that `measurements` contains several measurements of a
    ground-truth vector `X` with zero-mean noise, calculates an mostly-unbiased
    estimate of ||X||.

    This computes a fully unbiased estimate of ||X||^2. To estimate magnitude,
    we apply a square-root, which slightly biases the estimate of ||X||.
    This can return negative values.

    Implementation based loosely on:
    https://github.com/fwillett/cvVectorStats/blob/master/cvDistance.m

    Args:
        measurements (np.ndarray): n_observation x n_channel values
        subtract_mean (bool): if True, estimate ||X - mean(X)||

    Returns:
        magnitude_est: estimate of ||X||
            (or ||X - mean(X)|| if `subtract_mean`)

    """
    n_observation, n_channels = measurements.shape
    squared_magnitude_estimates = np.zeros(n_observation)
    # Crossvalidate each observation (group A) against the group of other
    # (group B) observations
    observation_indices = np.arange(n_observation)
    for groupA_index in observation_indices:
        groupB_indices = np.setdiff1d(observation_indices, groupA_index)

        # "group" A is a single measurement - no need to take mean
        groupA_mean = measurements[groupA_index]
        groupB_mean = measurements[groupB_indices].mean(axis=0)

        if subtract_mean:
            # Subtract channel-wise mean to for ||X - mean(X)||
            groupA_mean = groupA_mean - groupA_mean.mean()
            groupB_mean = groupB_mean - groupB_mean.mean()

        squared_magnitude_estimates[groupA_index] = np.dot(groupA_mean, groupB_mean)

    squared_magnitude = np.mean(squared_magnitude_estimates)
    magnitude_est = np.sign(squared_magnitude) * np.sqrt(abs(squared_magnitude))

    return magnitude_est


def _gen_default_cv_descriptor(dataset, descriptor):
    """ generates a default cv_descriptor for crossnobis
    This assumes that the first occurence each descriptor value forms the
    first group, the second occurence forms the second group, etc.
    """
    desc = dataset.obs_descriptors[descriptor]
    values, counts = np.unique(desc, return_counts=True)
    assert np.all(counts == counts[0]), (
        'cv_descriptor generation failed:\n'
        + 'different number of observations per pattern')
    n_repeats = counts[0]
    cv_descriptor = np.zeros_like(desc)
    for i_val in values:
        cv_descriptor[desc == i_val] = np.arange(n_repeats)
    return cv_descriptor


def _calc_pairwise_differences(measurements):
    n, m = measurements.shape
    diff = np.zeros((int(n * (n - 1) / 2), m))
    k = 0
    for i in range(measurements.shape[0]):
        for j in range(i+1, measurements.shape[0]):
            diff[k] = measurements[i] - measurements[j]
            k += 1
    return diff


def _parse_input(dataset, descriptor):
    if descriptor is None:
        measurements = dataset.measurements
        desc = np.arange(measurements.shape[0])
        descriptor = 'pattern'
    else:
        measurements, desc, _ = average_dataset_by(dataset, descriptor)
    return measurements, desc, descriptor


def _check_noise(noise, n_channel):
    """
    checks that a noise pattern is a matrix with correct dimension
    n_channel x n_channel

    Args:
        noise: noise input to be checked

    Returns:
        noise(np.ndarray): n_channel x n_channel noise precision matrix

    """
    if noise is None:
        pass
    elif isinstance(noise, np.ndarray) and noise.ndim == 2:
        assert np.all(noise.shape == (n_channel, n_channel))
    elif isinstance(noise, Iterable):
        for i in range(len(noise)):
            noise[i] = _check_noise(noise[i], n_channel)
    elif isinstance(noise, dict):
        for key in noise.keys():
            noise[key] = _check_noise(noise[key], n_channel)
    else:
        raise ValueError('noise(s) must have shape n_channel x n_channel')
    return noise
