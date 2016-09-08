""" Region Map
This file contains the code for reading GFF3 files into region maps
"""
import bisect
import os
import warnings
import pysam
import timeit
from collections import namedtuple
from functools import lru_cache

class AlignmentMap(dict):
    SamIn = namedtuple('InLine',
                       ['alignment_number',
                        'flag',
                        'cigar',
                        'rname_positions'])

    def __init__(self, path):
        self.update(self.read_alignment_map(path))

    @classmethod
    def read_alignment_map(cls, path):
        """Reads Alignment map SAM/BAM file into dictionary"""
        amap = {}
        samfile = pysam.AlignmentFile(path, 'r')
        for count, seq_line in enumerate(samfile):
            qname = seq_line.query_name
            amap.setdefault(qname,
                            cls.SamIn([0],
                            seq_line.flag,
                            seq_line.cigar,
                            []))
            amap[qname].alignment_number[0] += 1
            try:
                amap[qname].rname_positions.append((seq_line.reference_name,
                                                    seq_line.reference_start))
            except ValueError:
                warnings.warn('Reference Name is -1, Line #: {}'.format(count))

        return amap

def split_gen(s, delims):
    """iterates a delimited line"""
    start = 0
    for i, c in enumerate(s):
        if c in delims:
            yield s[start:i]
            start = i+1
    yield s[start:]

class Region(object):
    """Class that handels the region information in GFF3 files"""

    Gene = namedtuple('Gene', ['location', 'strand', 'features'])
    Feature = namedtuple('Feature', ['location', 'strand'])
    def __init__(self, length, strand):
        self.length = length
        self.strand = strand
        self.genes = dict()

    def add_feature(self, feature, location, strand, semicolon_params):
        """Adds either gene to self.genes or exon to a gene in self.genes
        """
        split_semi = split_gen(semicolon_params, ',:;=')
        if feature == 'exon':
            try:
                for i in range(6): next(split_semi)
                #parent_gene = next(split_semi)
                #print('Exon: {}'.format(parent_gene))
                bisect.insort_left(self.genes[next(split_semi)].features, self.Feature(location, strand))
            except KeyError:
                warnings.warn('Exon found that doesnt match a gene') #TODO elaborate more
        elif feature == 'gene':
            for i in range(4): next(split_semi)
            #gene_name = next(split_semi)
            #print('Gene: {}'.format(gene_name))
            self.genes.setdefault(next(split_semi), self.Gene(location, strand, []))


    Classification = namedtuple('Classification',
                                ['intergene', 'exons', 'introns', 'combos'])
    def classify_sequence(self, sequence_location):
        """Determines in read sequence is:
              exonic, intronic, intergenic, or a combination
        """
        exons, introns, combos = 0, 0, 0

        matching_genes = self.gene_location_match(sequence_location)
        if len(matching_genes) is 0:
            return Classification(1, 0, 0, 0)

        for match in matching_genes:
            feature_matches = self.overlapping_coordinate_match(match.value.features, sequence_location)
            if len(feature_matches) is 0:
                introns += 1

            for feature_match in feature_matches:
                if feature_match.lower != feature_match.upper:
                    combos += 1
                elif feature_match.lower and feature_match.upper:
                    exons += 1

        return Classification(False, exons, introns, combos)

    def gene_location_match(self, sequence_location):
        """Finds the gene(s) that a sequence aligns too
        Walks up or down from a binary coordinate match"""
        sorted_genes = sorted(self.genes.values())
        return self.overlapping_coordinate_match(sorted_genes,
                                                 sequence_location)

    @staticmethod
    def coordinate_relations(coordinate_pair, relation_coordinate_pair):
        """Returns weather the relation_coordinate_pair's uppper and lower
        bounds are within coordinate_pair
        """
        return (bool(coordinate_pair[0] <= relation_coordinate_pair[0] <= coordinate_pair[1]),
                bool(coordinate_pair[0] <= relation_coordinate_pair[1] <=  coordinate_pair[1]))

    Match = namedtuple('Match', ['index', 'lower', 'upper', 'value'])
    @classmethod
    def overlapping_coordinate_match(cls, sorted_coordinates, coordinate_pair):
        """Gets all matches in a sorted list of (possibly) overlapping
        coordinate pairs"""
        match1 = cls.binary_coordinate_match(sorted_coordinates,
                                             sequence_location)
        matches_upper = cls.sequential_coordinate_match(sorted_coordinates,
                                                        coordinate_pair,
                                                        start=match1.index+1)
        matches_lower = cls.sequential_coordinate_match(sorted_coordinates,
                                                        coordinate_pair,
                                                        start=match1.index-1,
                                                        step=-1)
        return [match1] + matches_lower + matches_upper

    @classmethod
    def binary_coordinate_match(cls, sorted_coordinates, coordinate_pair):
        """Trys to figure out if the coordinate_pair is in an ordered list of
        coordinate pairs using binary search
        Returns the coordinate_pair
        TODO:
            match overlapping genes
        """
        pair_average = (coordinate_pair[0]+coordinate_pair[1])/2
        high = len(sorted_coordinates)
        low = 0
        while low < high:
            mid = (low+high)//2
            midval = sorted_coordinates[mid]
            lower, upper = cls.coordinate_relations(midval.location, coordinate_pair)
            if upper or lower:
                return cls.Match(mid, lower, upper, midval)
            elif midval.location[0] > pair_average:
                high = mid
            elif midval.location[0] < pair_average:
                low = mid+1
            else:
                raise Exception('Unknown behavior') #TODO test
        return cls.Match(None, None, None, None)

    @classmethod
    def sequential_coordinate_match(cls, sorted_coordinates, coordinate_pair, start=0, step=1):
        """Searches for matches until none are found"""
        matches = []
        while True:
            try:
                current = sorted_coordinates[start]
            except IndexError:
                return matches

            lower, upper = cls.coordinate_relations(current.location, coordinate_pair)
            if lower or upper:
                matches.append(cls.Match(start, lower, upper, current))
                start += step
            else:
                return matches


class RegionMap(object):
    """Reads creates a feature location map from a gff file that can be
    used to determine gene attribute types from sequence location ranges

    Region Map Structure:
        {'RNAME': [gene: (([Features: (location, strand),], (coordinates: 0, 1))], Length}
    """
    Region = namedtuple('Region', ['genes', 'length'])
    def __init__(self, gff_path, accepted_features='exon'):
        if isinstance(accepted_features, str):
            accepted_features = tuple([accepted_features])
        self.feature_types = accepted_features
        print(accepted_features)
        self.rmap = self.read_gff(gff_path, feature_types=self.feature_types)

    @classmethod
    def read_gff(cls, gff_path, feature_types):
        """Reads a gff file into a region map hash"""
        region_map = {}
        feature_temp = {key: [] for key in feature_types}
        with open(gff_path, 'r') as gff:
            for count, line in enumerate(gff):
                try:
                    if line.startswith('#'):
                        continue
                    line_gen = split_gen(line, '\t ')
                    region = next(line_gen)
                    next(line_gen)
                    feature = next(line_gen)
                    location = (int(next(line_gen)), int(next(line_gen)))
                    next(line_gen)
                    strand = next(line_gen)
                    next(line_gen)
                    semicolon_params = next(line_gen)
                    #tmp_feature = cls.Feature(location, strand)
                    try:
                        region_map[region].add_feature(feature,
                                                       location,
                                                       strand,
                                                       semicolon_params)
                    except KeyError:
                        if feature == 'region':
                            region_map.setdefault(region,
                                                  Region(location[1],
                                                         strand))
                        else:
                            region_map.setdefault(region,
                                                  Region(None,
                                                         strand))
                            try:
                                region_map[region].add_feature(feature,
                                                               location,
                                                               strand,
                                                               semicolon_params)
                            except KeyError:
                                pass

                except StopIteration:
                    warnings.warn('Invalid line: {} ... skipped'.format(count))
        #return cls.calc_missing_region_lengths(region_map)
        return region_map

    @classmethod
    def calc_missing_region_lengths(cls, region_map):
        """Calculates region lengths for regions without a region line
        TODO: fix feature gathering
        """
        for key, region in region_map.items():
            if region.length is None:
                features = iter(region.features)
                largest = next(features)
                for feat in features:
                    if largest < feat.location[1]: largest = feat.location[1]
                region_map[key] = cls.Region(region.features, largest)
        return region_map

    @lru_cache(maxsize=None)
    def get_location_clasification(self,
                                   region_name,
                                   location_start,
                                   location_stop):
        """Gets location classification from region_map"""
        try:
            #self.rmap[region_name].binary_coordinate_match(
            pass
        except KeyError:
            warnings.warn('Region name {} not found'.format(region_name))
        for key, features in self.rmap[region_name].features.items():
            for feat_range, _ in features:
                start_flag = location_start in range(feat_range[0],
                                                     feat_range[1])
                stop_flag = location_stop in range(feat_range[0],
                                                   feat_range[1])

                if stop_flag is True and start_flag is True:
                    return key
                elif stop_flag != start_flag:
                    return 'combo'
                else:
                    return 'intron'


IN_GFF = '/disk/bioscratch/Will/Drop_Box/GCF_001266775.1_Austrofundulus_limnaeus-1.0_genomic_andMITO.gff'
IN_SAM = '/disk/bioscratch/Will/Drop_Box/HPF_small_RNA_022216.sam'
OUT_CSV = '/disk/bioscratch/Will/Drop_Box/SamStat_output.v2.csv'

if __name__ == '__main__':

    start = timeit.default_timer()
    rm = RegionMap(IN_GFF)
    end = timeit.default_timer()

    print('Total Program Time: {} seconds'.format(end-start))

    rm_list = list(rm.rmap.items())
    cur = None
    genes = None
    for i in range(10000):
        cur = rm_list[i]
        genes = list(rm_list[i][1].genes.items())
        if len(genes) > 100:
            break
    print(genes)
    #print(rm_list[0][1].genes)
    #print(len(rm_list))


