
import random
import pandas as pd
import warnings


class Gene:

    def __init__(self, g_id, g_weight):
        self.id = g_id
        self.weight = g_weight


class Chromosome:

    def __init__(self, genes, fitness=None):
        self.genes = genes
        self.fitness = fitness


class Pop:

    def __init__(self, pop, evals=None, avail_genes=None,
                 mut_prob=0.01):

        if type(pop[0]) is pd.Series:
            conv_pop = []
            for p, e in zip(pop, evals):
                d = p.to_dict()
                ids = list(d.keys())
                vals = list(d.values())
                genes = []
                for i, v in zip(ids, vals):
                    g = Gene(i, v)
                    genes.append(g)

                c = Chromosome(genes, fitness=e)
                conv_pop.append(c)
            pop = conv_pop.copy()

        self.pop = pop
        self.mut_prob = mut_prob
        # Useful for mutation (maximum number of alternatives)
        self.avail_genes = avail_genes

    def crossover(self, mutate=False):
        """
        :return:
            new population
        """
        pop = self.pop
        # crossover
        # pick n pop pairs of candidates (parents) based on their evaluation (fitness)
        children = []
        for _ in range(len(pop)):
            choices = pop
            weights = [c.fitness for c in pop]
            # parent1, parent2
            p1, p2 = random.choices(choices, weights=weights, k=2)
            # In case mutation is needed
            mut_choices = list(set(self.avail_genes) - (set(p1.genes) & set(p2.genes)))

            genes = []
            for g1, g2 in zip(p1.genes, p2.genes):
                g = random.choices([g1, g2], weights=[g1.weight, g2.weight], k=1)
                if mutate:
                    if random.random() > self.mut_prob:

                        rnd_id = random.choice(mut_choices)
                        # Weight is irrelevant, it will be calculated by the optimiser later
                        g = Gene(g_id=rnd_id, weight=None)

                genes.append(g)

            c = Chromosome(genes)
            children.append(c)

        self.pop = children.copy()
