from __future__ import division, absolute_import, print_function
from .. import affinitymat
from .. import nearest_neighbors
from .. import cluster
from .. import aggregator
from .. import core
from .. import util
from collections import defaultdict, OrderedDict, Counter
import numpy as np
import time
import sys
import gc


class TfModiscoSeqletsToPatternsFactory(object):

    def __init__(self, n_cores=20,
                       min_overlap_while_sliding=0.7,

                       #gapped kmer embedding arguments
                       alphabet_size=4,
                       kmer_len=8, num_gaps=3, num_mismatches=2,
                       gpu_batch_size=20,

                       nn_n_jobs=4,
                       nearest_neighbors_to_compute=500,

                       affmat_correlation_threshold=0.15,
                       filter_beyond_first_round=False,

                       tsne_perplexity = 10,
                       louvain_num_runs_and_levels_r1=[(200,-1)],
                       louvain_num_runs_and_levels_r2=[(200,-1)],
                       louvain_contin_runs_r1 = 50,
                       louvain_contin_runs_r2 = 50,
                       final_louvain_level_to_return=1,

                       frac_support_to_trim_to=0.2,
                       min_num_to_trim_to=30,
                       trim_to_window_size=30,
                       initial_flank_to_add=10,

                       prob_and_pertrack_sim_merge_thresholds=[
                        (0.0001,0.84), (0.00001, 0.87), (0.000001, 0.9)],

                       prob_and_pertrack_sim_dealbreaker_thresholds=[
                        (0.1,0.75), (0.01, 0.8), (0.001, 0.83),
                        (0.0000001,0.9)],

                       threshold_for_spurious_merge_detection=0.8,

                       min_similarity_for_seqlet_assignment=0.2,
                       final_min_cluster_size=30,

                       final_flank_to_add=10,
                       verbose=True):

        #affinity_mat calculation
        self.n_cores = n_cores
        self.min_overlap_while_sliding = min_overlap_while_sliding

        #gapped kmer embedding arguments
        self.alphabet_size = alphabet_size
        self.kmer_len = kmer_len
        self.num_gaps = num_gaps
        self.num_mismatches = num_mismatches
        self.gpu_batch_size = gpu_batch_size

        self.nn_n_jobs = nn_n_jobs
        self.nearest_neighbors_to_compute = nearest_neighbors_to_compute

        self.affmat_correlation_threshold = affmat_correlation_threshold
        self.filter_beyond_first_round = filter_beyond_first_round

        #affinity mat to tsne dist mat setting
        self.tsne_perplexity = tsne_perplexity

        #clustering settings
        self.louvain_num_runs_and_levels_r1 = louvain_num_runs_and_levels_r1
        self.louvain_num_runs_and_levels_r2 = louvain_num_runs_and_levels_r2
        self.louvain_contin_runs_r1 = louvain_contin_runs_r1
        self.louvain_contin_runs_r2 = louvain_contin_runs_r2
        self.final_louvain_level_to_return = final_louvain_level_to_return

        #postprocessor1 settings
        self.frac_support_to_trim_to = frac_support_to_trim_to
        self.min_num_to_trim_to = min_num_to_trim_to
        self.trim_to_window_size = trim_to_window_size
        self.initial_flank_to_add = initial_flank_to_add 

        #merging similar patterns
        self.prob_and_pertrack_sim_merge_thresholds =\
            prob_and_pertrack_sim_merge_thresholds
        self.prob_and_pertrack_sim_dealbreaker_thresholds =\
            prob_and_pertrack_sim_dealbreaker_thresholds

        self.threshold_for_spurious_merge_detection =\
            threshold_for_spurious_merge_detection

        #reassignment settings
        self.min_similarity_for_seqlet_assignment =\
            min_similarity_for_seqlet_assignment
        self.final_min_cluster_size = final_min_cluster_size

        #final postprocessor settings
        self.final_flank_to_add=final_flank_to_add

        #other settings
        self.verbose = verbose

    def get_jsonable_config(self):
        to_return =  OrderedDict([
                ('class_name', type(self).__name__),
                ('n_cores', self.n_cores),
                ('min_overlap_while_sliding', self.min_overlap_while_sliding),
                ('alphabet_size', self.alphabet_size),
                ('kmer_len', self.kmer_len),
                ('num_gaps', self.num_gaps),
                ('num_mismatches', self.num_mismatches),
                ('nn_n_jobs', self.nn_n_jobs),
                ('nearest_neighbors_to_compute',
                 self.nearest_neighbors_to_compute),
                ('affmat_correlation_threshold',
                 self.affmat_correlation_threshold),
                ('filter_beyond_first_round', filter_beyond_first_round),
                ('tsne_perplexity', self.tsne_perplexity),
                ('louvain_num_runs_and_levels_r1',
                 self.louvain_num_runs_and_levels_r1),
                ('louvain_num_runs_and_levels_r2',
                 self.louvain_num_runs_and_levels_r2),
                ('final_louvain_level_to_return',
                 self.final_louvain_level_to_return),
                ('louvain_contin_runs_r1',
                 self.louvain_contin_runs_r1),
                ('louvain_contin_runs_r2',
                 self.louvain_contin_runs_r2),
                ('frac_support_to_trim_to', self.frac_support_to_trim_to),
                ('min_num_to_trim_to', self.min_num_to_trim_to),
                ('trim_to_window_size', self.trim_to_window_size),
                ('initial_flank_to_add', self.initial_flank_to_add),
                ('prob_and_pertrack_sim_merge_thresholds',
                 self.prob_and_pertrack_sim_merge_thresholds),
                ('prob_and_pertrack_sim_dealbreaker_thresholds',
                 self.prob_and_pertrack_sim_dealbreaker_thresholds),
                ('threshold_for_spurious_merge_detection',
                 self.threshold_for_spurious_merge_detection),
                ('min_similarity_for_seqlet_assignment',
                 self.min_similarity_for_seqlet_assignment),
                ('final_min_cluster_size', self.final_min_cluster_size),
                ('final_flank_to_add', self.final_flank_to_add)]) 
        return to_return

    def __call__(self, track_set, onehot_track_name,
                       contrib_scores_track_names,
                       hypothetical_contribs_track_names,
                       track_signs,
                       other_comparison_track_names=[]):

        assert len(track_signs)==len(hypothetical_contribs_track_names)
        assert len(track_signs)==len(contrib_scores_track_names)

        seqlets_sorter = (lambda arr:
                          sorted(arr,
                                 key=lambda x:
                                      np.sum([np.sum(np.abs(x[track_name].fwd))
                                         for track_name
                                         in contrib_scores_track_names])))

        pattern_comparison_settings =\
            affinitymat.core.PatternComparisonSettings(
                track_names=hypothetical_contribs_track_names
                            +contrib_scores_track_names
                            +other_comparison_track_names, 
                track_transformer=affinitymat.L1Normalizer(), 
                min_overlap=self.min_overlap_while_sliding)

        #gapped kmer embedder
        gkmer_embedder = affinitymat.core.GappedKmerEmbedder(
            alphabet_size=self.alphabet_size,
            kmer_len=self.kmer_len,
            num_gaps=self.num_gaps,
            num_mismatches=self.num_mismatches,
            batch_size=self.gpu_batch_size,
            num_filters_to_retain=None,
            onehot_track_name=onehot_track_name,
            toscore_track_names_and_signs=list(
                zip(hypothetical_contribs_track_names,
                    [np.sign(x) for x in track_signs])),
            normalizer=affinitymat.core.MeanNormalizer())

        #affinity matrix from embeddings
        coarse_affmat_computer =\
            affinitymat.core.AffmatFromSeqletEmbeddings(
                seqlets_to_1d_embedder=gkmer_embedder,
                affinity_mat_from_1d=\
                    affinitymat.core.NumpyCosineSimilarity(
                        verbose=self.verbose,
                        gpu_batch_size=None),
                verbose=self.verbose)

        nearest_neighbors_computer = nearest_neighbors.ScikitNearestNeighbors(
            n_neighbors=self.nearest_neighbors_to_compute,
            nn_n_jobs=self.nn_n_jobs)  

        affmat_from_seqlets_with_nn_pairs =\
            affinitymat.core.AffmatFromSeqletsWithNNpairs(
                pattern_comparison_settings=pattern_comparison_settings,
                sim_metric_on_nn_pairs=\
                    affinitymat.core.ParallelCpuCrossMetricOnNNpairs(
                        n_cores=self.n_cores,
                        cross_metric_single_region=
                            affinitymat.core.CrossContinJaccardSingleRegion()))

        filter_mask_from_correlation =\
            affinitymat.core.FilterMaskFromCorrelation(
                correlation_threshold=self.affmat_correlation_threshold,
                verbose=self.verbose)

        aff_to_dist_mat = affinitymat.transformers.AffToDistViaInvLogistic() 
        density_adapted_affmat_transformer =\
            affinitymat.transformers.TsneConditionalProbs(
                perplexity=self.tsne_perplexity,
                aff_to_dist_mat=aff_to_dist_mat)

        #prepare the clusterers for the different rounds
        affmat_transformer_r1 = affinitymat.transformers.SymmetrizeByAddition(
                                probability_normalize=True)
        for n_runs, level_to_return in self.louvain_num_runs_and_levels_r1:
            affmat_transformer_r1 = affmat_transformer_r1.chain(
                affinitymat.transformers.LouvainMembershipAverage(
                    n_runs=n_runs,
                    level_to_return=level_to_return,
                    parallel_threads=self.n_cores))
        clusterer_r1 = cluster.core.LouvainCluster(
            level_to_return=self.final_louvain_level_to_return,
            affmat_transformer=affmat_transformer_r1,
            contin_runs=self.louvain_contin_runs_r1,
            verbose=self.verbose)

        affmat_transformer_r2 = affinitymat.transformers.SymmetrizeByAddition(
                                probability_normalize=True)
        for n_runs, level_to_return in self.louvain_num_runs_and_levels_r2:
            affmat_transformer_r2 = affmat_transformer_r2.chain(
                affinitymat.transformers.LouvainMembershipAverage(
                    n_runs=n_runs,
                    level_to_return=level_to_return,
                    parallel_threads=self.n_cores))
        clusterer_r2 = cluster.core.LouvainCluster(
            level_to_return=self.final_louvain_level_to_return,
            affmat_transformer=affmat_transformer_r2,
            contin_runs=self.louvain_contin_runs_r2,
            verbose=self.verbose)
        
        clusterer_per_round = [clusterer_r1, clusterer_r2]

        #prepare the seqlet aggregator
        expand_trim_expand1 =\
            aggregator.ExpandSeqletsToFillPattern(
                track_set=track_set,
                flank_to_add=self.initial_flank_to_add).chain(
            aggregator.TrimToBestWindow(
                window_size=self.trim_to_window_size,
                track_names=contrib_scores_track_names)).chain(
            aggregator.ExpandSeqletsToFillPattern(
                track_set=track_set,
                flank_to_add=self.initial_flank_to_add))
        postprocessor1 =\
            aggregator.TrimToFracSupport(
                        min_frac=self.frac_support_to_trim_to,
                        min_num=self.min_num_to_trim_to,
                        verbose=self.verbose)\
                      .chain(expand_trim_expand1)
        seqlet_aggregator = aggregator.GreedySeqletAggregator(
            pattern_aligner=core.CrossContinJaccardPatternAligner(
                pattern_comparison_settings=pattern_comparison_settings),
                seqlet_sort_metric=
                    lambda x: -sum([np.sum(np.abs(x[track_name].fwd)) for
                               track_name in contrib_scores_track_names]),
            postprocessor=postprocessor1)

        def sign_consistency_func(motif):
            motif_track_signs = [
                np.sign(np.sum(motif[contrib_scores_track_name].fwd)) for
                contrib_scores_track_name in contrib_scores_track_names]
            return all([(x==y) for x,y in zip(motif_track_signs, track_signs)])

        #prepare the similar patterns collapser
        pattern_to_pattern_sim_computer =\
            affinitymat.core.AffmatFromSeqletsWithNNpairs(
                pattern_comparison_settings=pattern_comparison_settings,
                sim_metric_on_nn_pairs=\
                    affinitymat.core.ParallelCpuCrossMetricOnNNpairs(
                        n_cores=self.n_cores,
                        cross_metric_single_region=\
                            affinitymat.core.CrossContinJaccardSingleRegion(),
                        verbose=False))

        #similarity settings for merging
        prob_and_sim_merge_thresholds =\
            [(x[0], x[1]*(len(contrib_scores_track_names)
                          +len(other_comparison_track_names)))
             for x in self.prob_and_pertrack_sim_merge_thresholds]
        prob_and_sim_dealbreaker_thresholds =\
            [(x[0], x[1]*(len(contrib_scores_track_names)
                          +len(other_comparison_track_names)))
             for x in self.prob_and_pertrack_sim_dealbreaker_thresholds]

        spurious_merge_detector = aggregator.DetectSpuriousMerging(
            track_names=contrib_scores_track_names,
            track_transformer=affinitymat.core.L1Normalizer(),
            affmat_from_1d=affinitymat.core.ContinJaccardSimilarity(
                            make_positive=True, verbose=False),
            diclusterer=cluster.core.LouvainCluster(
                            level_to_return=1,
                            max_clusters=2, contin_runs=20,
                            verbose=False),
            is_dissimilar_func=aggregator.PearsonCorrIsDissimilarFunc(
                        threshold=self.threshold_for_spurious_merge_detection,
                        verbose=self.verbose),
            min_in_subcluster=self.final_min_cluster_size)

        similar_patterns_collapser =\
            aggregator.DynamicDistanceSimilarPatternsCollapser(
                pattern_to_pattern_sim_computer=
                    pattern_to_pattern_sim_computer,
                aff_to_dist_mat=aff_to_dist_mat,
                pattern_aligner=core.CrossCorrelationPatternAligner(
                    pattern_comparison_settings=
                        affinitymat.core.PatternComparisonSettings(
                            track_names=(
                                contrib_scores_track_names+
                                other_comparison_track_names), 
                            track_transformer=
                                affinitymat.MeanNormalizer().chain(
                                affinitymat.MagnitudeNormalizer()), 
                            min_overlap=self.min_overlap_while_sliding)),
                collapse_condition=(lambda dist_prob, aligner_sim:
                    any([(dist_prob > x[0] and aligner_sim > x[1])
                         for x in prob_and_sim_merge_thresholds])),
                dealbreaker_condition=(lambda dist_prob, aligner_sim:
                    any([(dist_prob < x[0] and aligner_sim < x[1])              
                         for x in prob_and_sim_dealbreaker_thresholds])),
                postprocessor=postprocessor1,
                verbose=self.verbose) 

        seqlet_reassigner =\
           aggregator.ReassignSeqletsFromSmallClusters(
            seqlet_assigner=aggregator.AssignSeqletsByBestMetric(
                pattern_comparison_settings=pattern_comparison_settings,
                individual_aligner_metric=
                    core.get_best_alignment_crosscontinjaccard,
                matrix_affinity_metric=
                    affinitymat.core.CrossContinJaccardMultiCoreCPU(
                        verbose=self.verbose, n_cores=self.n_cores),
                min_similarity=self.min_similarity_for_seqlet_assignment),
            min_cluster_size=self.final_min_cluster_size,
            postprocessor=expand_trim_expand1,
            verbose=self.verbose) 

        final_postprocessor = aggregator.ExpandSeqletsToFillPattern(
                                        track_set=track_set,
                                        flank_to_add=self.final_flank_to_add) 

        return TfModiscoSeqletsToPatterns(
                seqlets_sorter=seqlets_sorter,
                coarse_affmat_computer=coarse_affmat_computer,
                nearest_neighbors_computer=nearest_neighbors_computer,
                affmat_from_seqlets_with_nn_pairs=
                    affmat_from_seqlets_with_nn_pairs, 
                filter_mask_from_correlation=filter_mask_from_correlation,
                filter_beyond_first_round=self.filter_beyond_first_round,
                density_adapted_affmat_transformer=
                    density_adapted_affmat_transformer,
                clusterer_per_round=clusterer_per_round,
                seqlet_aggregator=seqlet_aggregator,
                sign_consistency_func=sign_consistency_func,
                spurious_merge_detector=spurious_merge_detector,
                similar_patterns_collapser=similar_patterns_collapser,
                seqlet_reassigner=seqlet_reassigner,
                final_postprocessor=final_postprocessor,
                verbose=self.verbose)

    def save_hdf5(self, grp):
        grp.attrs['jsonable_config'] =\
            json.dumps(self.jsonable_config, indent=4, separators=(',', ': ')) 


class SeqletsToPatternsResults(object):

    def __init__(self,
                 patterns, seqlets, affmat, cluster_results,
                 total_time_taken, success=True, **kwargs):
        self.success = success
        self.patterns = patterns
        self.seqlets = seqlets
        self.affmat = affmat
        self.cluster_results = cluster_results
        self.total_time_taken = total_time_taken
        self.__dict__.update(**kwargs)

    def save_hdf5(self, grp):
        if (self.success):
            util.save_patterns(self.patterns,
                               grp.create_group("patterns"))
            grp.create_dataset("affmat", data=self.affmat) 
            self.cluster_results.save_hdf5(grp.create_group("cluster_results"))   
            #grp.attrs['jsonable_config'] =\
            #    json.dumps(self.jsonable_config, indent=4, separators=(',', ': ')) 
            grp.attrs['total_time_taken'] = self.total_time_taken


class AbstractSeqletsToPatterns(object):

    def __call__(self, seqlets):
        raise NotImplementedError()


class TfModiscoSeqletsToPatterns(AbstractSeqletsToPatterns):

    def __init__(self, seqlets_sorter, 
                       coarse_affmat_computer,
                       nearest_neighbors_computer,
                       affmat_from_seqlets_with_nn_pairs, 
                       filter_mask_from_correlation,
                       filter_beyond_first_round,
                       density_adapted_affmat_transformer,
                       clusterer_per_round,
                       seqlet_aggregator,
                       sign_consistency_func,
                       spurious_merge_detector,
                       similar_patterns_collapser,
                       seqlet_reassigner,
                       final_postprocessor,
                       verbose=True):

        self.seqlets_sorter = seqlets_sorter
        self.coarse_affmat_computer = coarse_affmat_computer
        self.nearest_neighbors_computer = nearest_neighbors_computer
        self.affmat_from_seqlets_with_nn_pairs =\
            affmat_from_seqlets_with_nn_pairs
        self.filter_mask_from_correlation = filter_mask_from_correlation
        self.filter_beyond_first_round = filter_beyond_first_round
        self.density_adapted_affmat_transformer =\
            density_adapted_affmat_transformer
        self.clusterer_per_round = clusterer_per_round 
        self.seqlet_aggregator = seqlet_aggregator
        self.sign_consistency_func = sign_consistency_func
        
        self.spurious_merge_detector = spurious_merge_detector
        self.similar_patterns_collapser = similar_patterns_collapser
        self.seqlet_reassigner = seqlet_reassigner
        self.final_postprocessor = final_postprocessor

        self.verbose = verbose


    def __call__(self, seqlets):

        seqlets = self.seqlets_sorter(seqlets)

        start = time.time()

        seqlets_sets = []
        coarse_affmats = []
        nn_affmats = []
        filtered_seqlets_sets = []
        filtered_affmats = []
        density_adapted_affmats = []
        cluster_results_sets = []
        cluster_to_motif_sets = []
        cluster_to_eliminated_motif_sets = []

        for round_idx, clusterer in enumerate(self.clusterer_per_round):
            for i in range(3): gc.collect()

            round_num = round_idx+1

            seqlets_sets.append(seqlets)
            
            if (len(seqlets)==0):
                if (self.verbose):
                    print("len(seqlets) is 0 - bailing!")
                return SeqletsToPatternsResults(
                        patterns=None,
                        seqlets=None,
                        affmat=None,
                        cluster_results=None, 
                        total_time_taken=None,
                        success=False)

            if (self.verbose):
                print("(Round "+str(round_num)+
                      ") num seqlets: "+str(len(seqlets)))
                print("(Round "+str(round_num)+") Computing coarse affmat")
                sys.stdout.flush()
            coarse_affmat = self.coarse_affmat_computer(seqlets)
            coarse_affmats.append(coarse_affmat)

            nn_start = time.time() 
            if (self.verbose):
                print("(Round "+str(round_num)+") Compute nearest neighbors"
                      +" from coarse affmat")
                sys.stdout.flush()

            seqlet_neighbors = self.nearest_neighbors_computer(coarse_affmat)

            if (self.verbose):
                print("Computed nearest neighbors in",
                      round(time.time()-nn_start,2),"s")
                sys.stdout.flush()

            nn_affmat_start = time.time() 
            if (self.verbose):
                print("(Round "+str(round_num)+") Computing affinity matrix"
                      +" on nearest neighbors")
                sys.stdout.flush()
            nn_affmat = self.affmat_from_seqlets_with_nn_pairs(
                                        seqlet_neighbors=seqlet_neighbors,
                                        seqlets=seqlets) 
            nn_affmats.append(nn_affmat)
            
            if (self.verbose):
                print("(Round "+str(round_num)+") Computed affinity matrix"
                      +" on nearest neighbors in",
                      round(time.time()-nn_affmat_start,2),"s")
                sys.stdout.flush()

            #filter by correlation
            if (round_idx == 0 or self.filter_beyond_first_round==True):
                filtered_rows_mask = self.filter_mask_from_correlation(
                                        main_affmat=nn_affmat,
                                        other_affmat=coarse_affmat) 
                if (self.verbose):
                    print("(Round "+str(round_num)+") Retained "
                          +str(np.sum(filtered_rows_mask))
                          +" rows out of "+str(len(filtered_rows_mask))
                          +" after filtering")
                    sys.stdout.flush()
            else:
                filtered_rows_mask = np.array([True for x in seqlets])
                if (self.verbose):
                    print("Not applying filtering for "
                          +"rounds above first round")
                    sys.stdout.flush()

            filtered_seqlets = [x[0] for x in
                       zip(seqlets, filtered_rows_mask) if (x[1])]
            filtered_seqlets_sets.append(filtered_seqlets)

            filtered_affmat =\
                nn_affmat[filtered_rows_mask][:,filtered_rows_mask]
            filtered_affmats.append(filtered_affmat)

            if (self.verbose):
                print("(Round "+str(round_num)+") Computing density "
                      +"adapted affmat")
                sys.stdout.flush() 

            density_adapted_affmat =\
                self.density_adapted_affmat_transformer(filtered_affmat)
            density_adapted_affmats.append(density_adapted_affmat)

            if (self.verbose):
                print("(Round "+str(round_num)+") Computing clustering")
                sys.stdout.flush() 

            cluster_results = clusterer(density_adapted_affmat)
            cluster_results_sets.append(cluster_results)
            num_clusters = max(cluster_results.cluster_indices+1)
            cluster_idx_counts = Counter(cluster_results.cluster_indices)
            if (self.verbose):
                print("Got "+str(num_clusters)
                      +" clusters after round "+str(round_num))
                print("Counts:")
                print(dict([x for x in cluster_idx_counts.items()]))
                sys.stdout.flush()

            if (self.verbose):
                print("(Round "+str(round_num)+") Aggregating seqlets"
                      +" in each cluster")
                sys.stdout.flush()

            cluster_to_seqlets = defaultdict(list) 
            assert len(filtered_seqlets)==len(cluster_results.cluster_indices)
            for seqlet,idx in zip(filtered_seqlets,
                                  cluster_results.cluster_indices):
                cluster_to_seqlets[idx].append(seqlet)

            cluster_to_eliminated_motif = OrderedDict()
            cluster_to_motif = OrderedDict()
            cluster_to_motif_sets.append(cluster_to_motif)
            cluster_to_eliminated_motif_sets.append(
                cluster_to_eliminated_motif)
            for i in range(num_clusters):
                if (self.verbose):
                    print("Aggregating for cluster "+str(i)+" with "
                          +str(len(cluster_to_seqlets[i]))+" seqlets")
                    sys.stdout.flush()
                motifs = self.seqlet_aggregator(cluster_to_seqlets[i])
                assert len(motifs)==1
                motif = motifs[0]
                if (self.sign_consistency_func(motif)):
                    cluster_to_motif[i] = motif
                else:
                    if (self.verbose):
                        print("Dropping cluster "+str(i)+
                              " with "+str(motif.num_seqlets)
                              +" seqlets due to sign disagreement")
                    cluster_to_eliminated_motif[i] = motif

            #obtain unique seqlets from adjusted motifs
            seqlets = dict([(y.exidx_start_end_string, y)
                             for x in cluster_to_motif.values()
                             for y in x.seqlets]).values()

        if (self.verbose):
            print("Got "+str(len(cluster_to_motif.values()))+" clusters")
            print("Splitting into subclusters...")
            sys.stdout.flush()

        split_patterns = self.spurious_merge_detector(
                            cluster_to_motif.values())

        #Now start merging patterns 
        if (self.verbose):
            print("Merging on "+str(len(split_patterns))+" clusters")
            sys.stdout.flush()
        merged_patterns, pattern_merge_hierarchy =\
            self.similar_patterns_collapser( 
                patterns=split_patterns, seqlets=seqlets) 
        merged_patterns = sorted(merged_patterns, key=lambda x: -x.num_seqlets)
        if (self.verbose):
            print("Got "+str(len(merged_patterns))+" patterns after merging")
            sys.stdout.flush()

        if (self.verbose):
            print("Performing seqlet reassignment")
            sys.stdout.flush()
        reassigned_patterns = self.seqlet_reassigner(merged_patterns)
        final_patterns = self.final_postprocessor(reassigned_patterns)
        if (self.verbose):
            print("Got "+str(len(final_patterns))
                  +" patterns after reassignment")
            sys.stdout.flush()

        total_time_taken = round(time.time()-start,2)
        if (self.verbose):
            print("Total time taken is "
                  +str(total_time_taken)+"s")
            sys.stdout.flush()

        results = SeqletsToPatternsResults(
            patterns=final_patterns,
            seqlets=filtered_seqlets, #last stage of filtered seqlets
            affmat=filtered_affmat,
            cluster_results=cluster_results, 
            total_time_taken=total_time_taken,
           
            seqlets_sets=seqlets_sets,
            coarse_affmats=coarse_affmats,
            nn_affmats=nn_affmats,
            filtered_seqlets_sets=filtered_seqlets_sets,
            filtered_affmats=filtered_affmats,
            density_adapted_affmats=density_adapted_affmats,
            cluster_results_sets=cluster_results_sets,
            cluster_to_motif_sets=cluster_to_motif_sets,
            cluster_to_eliminated_motif_sets=cluster_to_eliminated_motif_sets,

            merged_patterns=merged_patterns,
            pattern_merge_hierarchy=pattern_merge_hierarchy,
            reassigned_patterns=reassigned_patterns)

        return results 


class TfModiscoSeqletsToPatternsFactoryDev(object):

    def __init__(self, n_cores=20,
                       min_overlap_while_sliding=0.7,

                       #gapped kmer embedding arguments
                       alphabet_size=4,
                       kmer_len=8, num_gaps=3, num_mismatches=2,
                       gpu_batch_size=20,

                       nn_n_jobs=4,
                       nearest_neighbors_to_compute=500,

                       affmat_correlation_threshold=0.15,
                       filter_beyond_first_round=False,

                       tsne_perplexity = 10,
                       louvain_num_runs_and_levels_r1=[(200,-1)],
                       louvain_num_runs_and_levels_r2=[(200,-1)],
                       louvain_contin_runs_r1 = 50,
                       louvain_contin_runs_r2 = 50,
                       final_louvain_level_to_return=1,

                       frac_support_to_trim_to=0.2,
                       min_num_to_trim_to=30,
                       trim_to_window_size=30,
                       initial_flank_to_add=10,

                       prob_and_pertrack_sim_merge_thresholds=[
                        (0.0001,0.84), (0.00001, 0.87), (0.000001, 0.9)],

                       prob_and_pertrack_sim_dealbreaker_thresholds=[
                        (0.1,0.75), (0.01, 0.8), (0.001, 0.83),
                        (0.0000001,0.9)],

                       threshold_for_spurious_merge_detection=0.8,

                       min_similarity_for_seqlet_assignment=0.2,
                       final_min_cluster_size=30,

                       final_flank_to_add=10,
                       verbose=True):

        print("\n\n!!!!THIS IS THE DEV VERSION!!!!!\n\n")

        #affinity_mat calculation
        self.n_cores = n_cores
        self.min_overlap_while_sliding = min_overlap_while_sliding

        #gapped kmer embedding arguments
        self.alphabet_size = alphabet_size
        self.kmer_len = kmer_len
        self.num_gaps = num_gaps
        self.num_mismatches = num_mismatches
        self.gpu_batch_size = gpu_batch_size

        self.nn_n_jobs = nn_n_jobs
        self.nearest_neighbors_to_compute = nearest_neighbors_to_compute

        self.affmat_correlation_threshold = affmat_correlation_threshold
        self.filter_beyond_first_round = filter_beyond_first_round

        #affinity mat to tsne dist mat setting
        self.tsne_perplexity = tsne_perplexity

        #clustering settings
        self.louvain_num_runs_and_levels_r1 = louvain_num_runs_and_levels_r1
        self.louvain_num_runs_and_levels_r2 = louvain_num_runs_and_levels_r2
        self.louvain_contin_runs_r1 = louvain_contin_runs_r1
        self.louvain_contin_runs_r2 = louvain_contin_runs_r2
        self.final_louvain_level_to_return = final_louvain_level_to_return

        #postprocessor1 settings
        self.frac_support_to_trim_to = frac_support_to_trim_to
        self.min_num_to_trim_to = min_num_to_trim_to
        self.trim_to_window_size = trim_to_window_size
        self.initial_flank_to_add = initial_flank_to_add 

        #merging similar patterns
        self.prob_and_pertrack_sim_merge_thresholds =\
            prob_and_pertrack_sim_merge_thresholds
        self.prob_and_pertrack_sim_dealbreaker_thresholds =\
            prob_and_pertrack_sim_dealbreaker_thresholds

        self.threshold_for_spurious_merge_detection =\
            threshold_for_spurious_merge_detection

        #reassignment settings
        self.min_similarity_for_seqlet_assignment =\
            min_similarity_for_seqlet_assignment
        self.final_min_cluster_size = final_min_cluster_size

        #final postprocessor settings
        self.final_flank_to_add=final_flank_to_add

        #other settings
        self.verbose = verbose

    def get_jsonable_config(self):
        to_return =  OrderedDict([
                ('dev', 'dev')]) 
        return to_return

    def __call__(self, track_set, onehot_track_name,
                       contrib_scores_track_names,
                       hypothetical_contribs_track_names,
                       track_signs,
                       other_comparison_track_names=[]):

        assert len(track_signs)==len(hypothetical_contribs_track_names)
        assert len(track_signs)==len(contrib_scores_track_names)

        seqlets_sorter = (lambda arr:
                          sorted(arr,
                                 key=lambda x:
                                      np.sum([np.sum(np.abs(x[track_name].fwd))
                                         for track_name
                                         in contrib_scores_track_names])))

        pattern_comparison_settings =\
            affinitymat.core.PatternComparisonSettings(
                track_names=hypothetical_contribs_track_names
                            +contrib_scores_track_names
                            +other_comparison_track_names, 
                track_transformer=affinitymat.L1Normalizer(), 
                min_overlap=self.min_overlap_while_sliding)

        #gapped kmer embedder
        gkmer_embedder = affinitymat.core.GappedKmerEmbedder(
            alphabet_size=self.alphabet_size,
            kmer_len=self.kmer_len,
            num_gaps=self.num_gaps,
            num_mismatches=self.num_mismatches,
            batch_size=self.gpu_batch_size,
            num_filters_to_retain=None,
            onehot_track_name=onehot_track_name,
            toscore_track_names_and_signs=list(
                zip(hypothetical_contribs_track_names,
                    [np.sign(x) for x in track_signs])),
            normalizer=affinitymat.core.MeanNormalizer())

        #affinity matrix from embeddings
        coarse_affmat_computer =\
            affinitymat.core.AffmatFromSeqletEmbeddings(
                seqlets_to_1d_embedder=gkmer_embedder,
                affinity_mat_from_1d=\
                    affinitymat.core.NumpyCosineSimilarity(
                        verbose=self.verbose,
                        gpu_batch_size=None),
                verbose=self.verbose)

        nearest_neighbors_computer = nearest_neighbors.ScikitNearestNeighbors(
            n_neighbors=self.nearest_neighbors_to_compute,
            nn_n_jobs=self.nn_n_jobs)  

        affmat_from_seqlets_with_nn_pairs =\
            affinitymat.core.AffmatFromSeqletsWithNNpairs(
                pattern_comparison_settings=pattern_comparison_settings,
                sim_metric_on_nn_pairs=\
                    affinitymat.core.ParallelCpuCrossMetricOnNNpairs(
                        n_cores=self.n_cores,
                        cross_metric_single_region=
                            affinitymat.core.CrossContinJaccardSingleRegion()))

        filter_mask_from_correlation =\
            affinitymat.core.FilterMaskFromCorrelation(
                correlation_threshold=self.affmat_correlation_threshold,
                verbose=self.verbose)

        aff_to_dist_mat = affinitymat.transformers.AffToDistViaInvLogistic() 

        density_adapted_affmat_transformer = lambda x: x
            #affinitymat.transformers.TsneConditionalProbs(
            #    perplexity=self.tsne_perplexity,
            #    aff_to_dist_mat=aff_to_dist_mat)

        #prepare the clusterers for the different rounds
        affmat_transformer_r1 = lambda x:x #affinitymat.transformers.SymmetrizeByAddition(
                                #probability_normalize=True)
        #for n_runs, level_to_return in self.louvain_num_runs_and_levels_r1:
        #    affmat_transformer_r1 = affmat_transformer_r1.chain(
        #        affinitymat.transformers.LouvainMembershipAverage(
        #            n_runs=n_runs,
        #            level_to_return=level_to_return,
        #            parallel_threads=self.n_cores))
        clusterer_r1 = cluster.core.HDbScanCluster(
                        aff_to_dist_mat=aff_to_dist_mat)#cluster.core.LouvainCluster(
            #level_to_return=self.final_louvain_level_to_return,
            #affmat_transformer=affmat_transformer_r1,
            #contin_runs=self.louvain_contin_runs_r1,
            #verbose=self.verbose)

        affmat_transformer_r2 = lambda x: x #affinitymat.transformers.SymmetrizeByAddition(
                                #probability_normalize=True)
        #for n_runs, level_to_return in self.louvain_num_runs_and_levels_r2:
        #    affmat_transformer_r2 = affmat_transformer_r2.chain(
        #        affinitymat.transformers.LouvainMembershipAverage(
        #            n_runs=n_runs,
        #            level_to_return=level_to_return,
        #            parallel_threads=self.n_cores))
        clusterer_r2 = cluster.core.HDbScanCluster(
                        aff_to_dist_mat=aff_to_dist_mat) #cluster.core.LouvainCluster(
            #level_to_return=self.final_louvain_level_to_return,
            #affmat_transformer=affmat_transformer_r2,
            #contin_runs=self.louvain_contin_runs_r2,
            #verbose=self.verbose)
        
        clusterer_per_round = [clusterer_r1, clusterer_r2]

        #prepare the seqlet aggregator
        expand_trim_expand1 =\
            aggregator.ExpandSeqletsToFillPattern(
                track_set=track_set,
                flank_to_add=self.initial_flank_to_add).chain(
            aggregator.TrimToBestWindow(
                window_size=self.trim_to_window_size,
                track_names=contrib_scores_track_names)).chain(
            aggregator.ExpandSeqletsToFillPattern(
                track_set=track_set,
                flank_to_add=self.initial_flank_to_add))
        postprocessor1 =\
            aggregator.TrimToFracSupport(
                        min_frac=self.frac_support_to_trim_to,
                        min_num=self.min_num_to_trim_to,
                        verbose=self.verbose)\
                      .chain(expand_trim_expand1)
        seqlet_aggregator = aggregator.GreedySeqletAggregator(
            pattern_aligner=core.CrossContinJaccardPatternAligner(
                pattern_comparison_settings=pattern_comparison_settings),
                seqlet_sort_metric=
                    lambda x: -sum([np.sum(np.abs(x[track_name].fwd)) for
                               track_name in contrib_scores_track_names]),
            postprocessor=postprocessor1)

        def sign_consistency_func(motif):
            motif_track_signs = [
                np.sign(np.sum(motif[contrib_scores_track_name].fwd)) for
                contrib_scores_track_name in contrib_scores_track_names]
            return all([(x==y) for x,y in zip(motif_track_signs, track_signs)])

        #prepare the similar patterns collapser
        pattern_to_pattern_sim_computer =\
            affinitymat.core.AffmatFromSeqletsWithNNpairs(
                pattern_comparison_settings=pattern_comparison_settings,
                sim_metric_on_nn_pairs=\
                    affinitymat.core.ParallelCpuCrossMetricOnNNpairs(
                        n_cores=self.n_cores,
                        cross_metric_single_region=\
                            affinitymat.core.CrossContinJaccardSingleRegion(),
                        verbose=False))

        #similarity settings for merging
        prob_and_sim_merge_thresholds =\
            [(x[0], x[1]*(len(contrib_scores_track_names)
                          +len(other_comparison_track_names)))
             for x in self.prob_and_pertrack_sim_merge_thresholds]
        prob_and_sim_dealbreaker_thresholds =\
            [(x[0], x[1]*(len(contrib_scores_track_names)
                          +len(other_comparison_track_names)))
             for x in self.prob_and_pertrack_sim_dealbreaker_thresholds]

        spurious_merge_detector = aggregator.DetectSpuriousMerging(
            track_names=contrib_scores_track_names,
            track_transformer=affinitymat.core.L1Normalizer(),
            affmat_from_1d=affinitymat.core.ContinJaccardSimilarity(
                            make_positive=True, verbose=False),
            diclusterer=cluster.core.LouvainCluster(
                            level_to_return=1,
                            max_clusters=2, contin_runs=20,
                            verbose=False),
            is_dissimilar_func=aggregator.PearsonCorrIsDissimilarFunc(
                        threshold=self.threshold_for_spurious_merge_detection,
                        verbose=self.verbose),
            min_in_subcluster=self.final_min_cluster_size)

        similar_patterns_collapser =\
            aggregator.DynamicDistanceSimilarPatternsCollapser(
                pattern_to_pattern_sim_computer=
                    pattern_to_pattern_sim_computer,
                aff_to_dist_mat=aff_to_dist_mat,
                pattern_aligner=core.CrossCorrelationPatternAligner(
                    pattern_comparison_settings=
                        affinitymat.core.PatternComparisonSettings(
                            track_names=(
                                contrib_scores_track_names+
                                other_comparison_track_names), 
                            track_transformer=
                                affinitymat.MeanNormalizer().chain(
                                affinitymat.MagnitudeNormalizer()), 
                            min_overlap=self.min_overlap_while_sliding)),
                collapse_condition=(lambda dist_prob, aligner_sim:
                    any([(dist_prob > x[0] and aligner_sim > x[1])
                         for x in prob_and_sim_merge_thresholds])),
                dealbreaker_condition=(lambda dist_prob, aligner_sim:
                    any([(dist_prob < x[0] and aligner_sim < x[1])              
                         for x in prob_and_sim_dealbreaker_thresholds])),
                postprocessor=postprocessor1,
                verbose=self.verbose) 

        seqlet_reassigner =\
           aggregator.ReassignSeqletsFromSmallClusters(
            seqlet_assigner=aggregator.AssignSeqletsByBestMetric(
                pattern_comparison_settings=pattern_comparison_settings,
                individual_aligner_metric=
                    core.get_best_alignment_crosscontinjaccard,
                matrix_affinity_metric=
                    affinitymat.core.CrossContinJaccardMultiCoreCPU(
                        verbose=self.verbose, n_cores=self.n_cores),
                min_similarity=self.min_similarity_for_seqlet_assignment),
            min_cluster_size=self.final_min_cluster_size,
            postprocessor=expand_trim_expand1,
            verbose=self.verbose) 

        final_postprocessor = aggregator.ExpandSeqletsToFillPattern(
                                        track_set=track_set,
                                        flank_to_add=self.final_flank_to_add) 

        return TfModiscoSeqletsToPatternsDev(
                seqlets_sorter=seqlets_sorter,
                coarse_affmat_computer=coarse_affmat_computer,
                nearest_neighbors_computer=nearest_neighbors_computer,
                affmat_from_seqlets_with_nn_pairs=
                    affmat_from_seqlets_with_nn_pairs, 
                filter_mask_from_correlation=filter_mask_from_correlation,
                filter_beyond_first_round=self.filter_beyond_first_round,
                density_adapted_affmat_transformer=
                    density_adapted_affmat_transformer,
                clusterer_per_round=clusterer_per_round,
                seqlet_aggregator=seqlet_aggregator,
                sign_consistency_func=sign_consistency_func,
                spurious_merge_detector=spurious_merge_detector,
                similar_patterns_collapser=similar_patterns_collapser,
                seqlet_reassigner=seqlet_reassigner,
                final_postprocessor=final_postprocessor,
                verbose=self.verbose)

    def save_hdf5(self, grp):
        grp.attrs['jsonable_config'] =\
            json.dumps(self.jsonable_config, indent=4, separators=(',', ': ')) 


class TfModiscoSeqletsToPatternsDev(AbstractSeqletsToPatterns):

    def __init__(self, seqlets_sorter, 
                       coarse_affmat_computer,
                       nearest_neighbors_computer,
                       affmat_from_seqlets_with_nn_pairs, 
                       filter_mask_from_correlation,
                       filter_beyond_first_round,
                       density_adapted_affmat_transformer,
                       clusterer_per_round,
                       seqlet_aggregator,
                       sign_consistency_func,
                       spurious_merge_detector,
                       similar_patterns_collapser,
                       seqlet_reassigner,
                       final_postprocessor,
                       verbose=True):

        self.seqlets_sorter = seqlets_sorter
        self.coarse_affmat_computer = coarse_affmat_computer
        self.nearest_neighbors_computer = nearest_neighbors_computer
        self.affmat_from_seqlets_with_nn_pairs =\
            affmat_from_seqlets_with_nn_pairs
        self.filter_mask_from_correlation = filter_mask_from_correlation
        self.filter_beyond_first_round = filter_beyond_first_round
        self.density_adapted_affmat_transformer =\
            density_adapted_affmat_transformer
        self.clusterer_per_round = clusterer_per_round 
        self.seqlet_aggregator = seqlet_aggregator
        self.sign_consistency_func = sign_consistency_func
        
        self.spurious_merge_detector = spurious_merge_detector
        self.similar_patterns_collapser = similar_patterns_collapser
        self.seqlet_reassigner = seqlet_reassigner
        self.final_postprocessor = final_postprocessor

        self.verbose = verbose


    def __call__(self, seqlets):

        seqlets = self.seqlets_sorter(seqlets)

        start = time.time()

        seqlets_sets = []
        coarse_affmats = []
        nn_affmats = []
        filtered_seqlets_sets = []
        filtered_affmats = []
        density_adapted_affmats = []
        cluster_results_sets = []
        cluster_to_motif_sets = []
        cluster_to_eliminated_motif_sets = []

        for round_idx, clusterer in enumerate(self.clusterer_per_round):
            for i in range(3): gc.collect()

            round_num = round_idx+1

            seqlets_sets.append(seqlets)

            if (self.verbose):
                print("(Round "+str(round_num)+
                      ") num seqlets: "+str(len(seqlets)))
                print("(Round "+str(round_num)+") Computing coarse affmat")
                sys.stdout.flush()
            coarse_affmat = self.coarse_affmat_computer(seqlets)
            coarse_affmats.append(coarse_affmat)

            nn_start = time.time() 
            if (self.verbose):
                print("(Round "+str(round_num)+") Compute nearest neighbors"
                      +" from coarse affmat")
                sys.stdout.flush()

            seqlet_neighbors = self.nearest_neighbors_computer(coarse_affmat)

            if (self.verbose):
                print("Computed nearest neighbors in",
                      round(time.time()-nn_start,2),"s")
                sys.stdout.flush()

            nn_affmat_start = time.time() 
            if (self.verbose):
                print("(Round "+str(round_num)+") Computing affinity matrix"
                      +" on nearest neighbors")
                sys.stdout.flush()
            nn_affmat = self.affmat_from_seqlets_with_nn_pairs(
                                        seqlet_neighbors=seqlet_neighbors,
                                        seqlets=seqlets) 
            nn_affmats.append(nn_affmat)
            
            if (self.verbose):
                print("(Round "+str(round_num)+") Computed affinity matrix"
                      +" on nearest neighbors in",
                      round(time.time()-nn_affmat_start,2),"s")
                sys.stdout.flush()

            #filter by correlation
            if (round_idx == 0 or self.filter_beyond_first_round==True):
                filtered_rows_mask = self.filter_mask_from_correlation(
                                        main_affmat=nn_affmat,
                                        other_affmat=coarse_affmat) 
                if (self.verbose):
                    print("(Round "+str(round_num)+") Retained "
                          +str(np.sum(filtered_rows_mask))
                          +" rows out of "+str(len(filtered_rows_mask))
                          +" after filtering")
                    sys.stdout.flush()
            else:
                filtered_rows_mask = np.array([True for x in seqlets])
                if (self.verbose):
                    print("Not applying filtering for "
                          +"rounds above first round")
                    sys.stdout.flush()

            filtered_seqlets = [x[0] for x in
                       zip(seqlets, filtered_rows_mask) if (x[1])]
            filtered_seqlets_sets.append(filtered_seqlets)

            filtered_affmat =\
                nn_affmat[filtered_rows_mask][:,filtered_rows_mask]
            filtered_affmats.append(filtered_affmat)

            if (self.verbose):
                print("(Round "+str(round_num)+") Computing density "
                      +"adapted affmat")
                sys.stdout.flush() 

            density_adapted_affmat =\
                self.density_adapted_affmat_transformer(filtered_affmat)
            density_adapted_affmats.append(density_adapted_affmat)

            if (self.verbose):
                print("(Round "+str(round_num)+") Computing clustering")
                sys.stdout.flush() 

            cluster_results = clusterer(density_adapted_affmat)
            cluster_results_sets.append(cluster_results)
            num_clusters = max(cluster_results.cluster_indices+1)
            cluster_idx_counts = Counter(cluster_results.cluster_indices)
            if (self.verbose):
                print("Got "+str(num_clusters)
                      +" clusters after round "+str(round_num))
                print("Counts:")
                print(dict([x for x in cluster_idx_counts.items()]))
                sys.stdout.flush()

            if (self.verbose):
                print("(Round "+str(round_num)+") Aggregating seqlets"
                      +" in each cluster")
                sys.stdout.flush()

            cluster_to_seqlets = defaultdict(list) 
            assert len(filtered_seqlets)==len(cluster_results.cluster_indices)
            for seqlet,idx in zip(filtered_seqlets,
                                  cluster_results.cluster_indices):
                cluster_to_seqlets[idx].append(seqlet)

            cluster_to_eliminated_motif = OrderedDict()
            cluster_to_motif = OrderedDict()
            cluster_to_motif_sets.append(cluster_to_motif)
            cluster_to_eliminated_motif_sets.append(
                cluster_to_eliminated_motif)
            for i in range(num_clusters):
                if (self.verbose):
                    print("Aggregating for cluster "+str(i)+" with "
                          +str(len(cluster_to_seqlets[i]))+" seqlets")
                    sys.stdout.flush()
                motifs = self.seqlet_aggregator(cluster_to_seqlets[i])
                assert len(motifs)==1
                motif = motifs[0]
                if (self.sign_consistency_func(motif)):
                    cluster_to_motif[i] = motif
                else:
                    if (self.verbose):
                        print("Dropping cluster "+str(i)+
                              " with "+str(motif.num_seqlets)
                              +" seqlets due to sign disagreement")
                    cluster_to_eliminated_motif[i] = motif

            #obtain unique seqlets from adjusted motifs
            seqlets = dict([(y.exidx_start_end_string, y)
                             for x in cluster_to_motif.values()
                             for y in x.seqlets]).values()

        if (self.verbose):
            print("Got "+str(len(cluster_to_motif.values()))+" clusters")
            print("Splitting into subclusters...")
            sys.stdout.flush()

        split_patterns = self.spurious_merge_detector(
                            cluster_to_motif.values())

        #Now start merging patterns 
        if (self.verbose):
            print("Merging on "+str(len(split_patterns))+" clusters")
            sys.stdout.flush()
        merged_patterns, pattern_merge_hierarchy =\
            self.similar_patterns_collapser( 
                patterns=split_patterns, seqlets=seqlets) 
        merged_patterns = sorted(merged_patterns, key=lambda x: -x.num_seqlets)
        if (self.verbose):
            print("Got "+str(len(merged_patterns))+" patterns after merging")
            sys.stdout.flush()

        if (self.verbose):
            print("Performing seqlet reassignment")
            sys.stdout.flush()
        reassigned_patterns = self.seqlet_reassigner(merged_patterns)
        final_patterns = self.final_postprocessor(reassigned_patterns)
        if (self.verbose):
            print("Got "+str(len(final_patterns))
                  +" patterns after reassignment")
            sys.stdout.flush()

        total_time_taken = round(time.time()-start,2)
        if (self.verbose):
            print("Total time taken is "
                  +str(total_time_taken)+"s")
            sys.stdout.flush()

        results = SeqletsToPatternsResults(
            patterns=final_patterns,
            seqlets=filtered_seqlets, #last stage of filtered seqlets
            affmat=filtered_affmat,
            cluster_results=cluster_results, 
            total_time_taken=total_time_taken,
           
            seqlets_sets=seqlets_sets,
            coarse_affmats=coarse_affmats,
            nn_affmats=nn_affmats,
            filtered_seqlets_sets=filtered_seqlets_sets,
            filtered_affmats=filtered_affmats,
            density_adapted_affmats=density_adapted_affmats,
            cluster_results_sets=cluster_results_sets,
            cluster_to_motif_sets=cluster_to_motif_sets,
            cluster_to_eliminated_motif_sets=cluster_to_eliminated_motif_sets,

            merged_patterns=merged_patterns,
            pattern_merge_hierarchy=pattern_merge_hierarchy,
            reassigned_patterns=reassigned_patterns)

        return results 
