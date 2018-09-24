
def main(tcs, d_filters):

    for k, v in d_filters.items():
        tcs = tcs[tcs[k] <= v]

    return tcs
