import matplotlib.pyplot as plt
import numpy as np
import scipy.stats as stats
import math
import numpy
import sys
import matplotlib.pyplot as plt
import seaborn as sns


def print_statistical_data(delay_array):
    print('mean: ', numpy.mean(delay_array))
    print('var: ', numpy.var(delay_array))
    print('std: ', numpy.std(delay_array))
    print('min: ', numpy.min(delay_array))
    print('max: ', numpy.max(delay_array))


def plot_timewise(delay_array):
    plt.plot(delay_array)
    plt.show()

def plot_normal_dist(delay_array):
    
    # distribution of delay_array
    sns.distplot(delay_array, color='red')
    
    # normal distribution based on mean, variance
    size = len(delay_array)
    mu = numpy.mean(delay_array)
    variance = numpy.var(delay_array)
    sigma = math.sqrt(variance)
    x = np.linspace(mu - 3*sigma, mu + 3*sigma, size)
    plt.plot(x, stats.norm.pdf(x, mu, sigma))

    # show
    plt.show()


if __name__ == '__main__':
    
    delay_array = []
    # count = 100
    count = input("Please input the number of count to ping : ")
    filename = 'ping'+str(count)
    print('filename: ', filename)

    with open(filename, 'r') as f:
        # delay_array = [list(map(float, f.readline())) for _ in range(count)]
        for line in f.readlines():
            delay_array.append(float(line))
    
    # print_statistical_data(delay_array)
    # plot_timewise(delay_array)
    # print('---\n', delay_array)
    plot_normal_dist(delay_array)
    