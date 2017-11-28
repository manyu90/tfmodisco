import matplotlib.pyplot as plt
import numpy as np
import plotly
from plotly.offline import init_notebook_mode, plot_mpl,plot
import base64
import sys
from modisco.core import *
from modisco.visualization.viz_sequence import *
from modisco.visualization.matplotlibhelpers import *
from enum import Enum

class ImCategory(Enum):
    HEATMAP=0,
    SCATTERPLOT=1
    HISTOGRAM=2
    

def load_image(image,data=None,im_category=None,dim='""'):
    """
    Determines whether 'image' is a string 
    or a matplotlib figure handle. 
    Loads the image accordingly
    Returns a string with a '<div>' entity for embedding into html. 
    """
    if type(image)==plt.Figure:
        if im_category==ImCategory.HEATMAP:
            #special loading procedure for heatmaps, must also pass in source data.
            plotly_fig = plotly.tools.mpl_to_plotly(image)
            image_div=None
            plotly_fig['data']=[dict(z=data, type="heatmap")]
            image_div=plot(plotly_fig, include_plotlyjs=False, output_type='div')
        else:
            image_div=plot_mpl(image,output_type='div')
    elif type(image)==str:
        encoded = base64.b64encode(open(image, "rb").read())
        image_tag='<img src="data:image/png;base64,'+encoded+' '+dim+'>'
        image_div='<div>'+image_tag+'</div>'
    else:
        raise(Exception("Invalid file format for image, must be either str or plt.Figure"))
    return image_div



class VDataset(object):
    """
    Inputs: 
    all are optional. 
    metaclusters_heatmap -- object of type VAllMetaclusterHeatmap
    per_task_histograms -- list of VHistogram objects 
    metaclusters -- list of VMetaCluster objects 
    """

    def __init__(self,
                 metaclusters_heatmap=None,
                 per_task_histograms=[],
                 metaclusters=[],
                 title=None
                 
                 
    ):
        self.metaclusters_heatmap=metaclusters_heatmap
        self.per_task_histograms=per_task_histograms
        self.metaclusters=metaclusters
        self.title=title
        
        
class VCluster(object):
    """
    Inputs: 
    all are optional. 
    tsne_embedding -- VTsne object 
    tsne_embedding_denoised -- VTsne_denoised
 object 
    aggregate_motif -- VPattern object 
    example_seqlets -- list of VSeqlet objects 
    """
    def __init__(self,
                 tsne_embedding=None,
                 aggregate_motif=None,
                 example_seqlets=[],
                 
    ):
        self.tsne_embedding=tsne_embedding
        self.aggregate_motif=aggregate_motif
        self.example_seqlets=example_seqlets 
        
class VMetaCluster(object):
    """
    Inputs:
    all are optional. 
    tsne_embedding -- VTsne object 
    tsne_embedding_denoised -- VTsne_denoised object 
    clusters -- list of VCluster objects 
    """

    def __init__(self,
                 tsne_embedding=None,
                 tsne_embedding_denoised=None,
                 clusters=[]):
        self.clusters=clusters
        self.tsne_embedding=tsne_embedding 
        self.tsne_embedding_denoised=tsne_embedding_denoised


class VAllMetaclusterHeatmap(object):
    """
    Heatmap of all metaclusters in the dataset. 
    
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle 
    
    cluster_id_to_mean: dictionary mapping a cluster id to the cluster mean 
    cluster_id_to_num_seqlets_in_cluster: a dictionary mapping a cluster id to the number of seqlets in the cluster 
    """
    def __init__(self,image=None,data=None,im_category=ImCategory.HEATMAP,
                 cluster_id_to_mean={},
                 cluster_id_to_num_seqlets_in_cluster={}):
        self.image=load_image(image,
                              data=data,
                              im_category=im_category,
                              dim="height=\"400px\"")
        self.cluster_id_to_mean=cluster_id_to_mean
        self.cluster_id_to_num_seqlets_in_cluster=cluster_id_to_num_seqlets_in_cluster        
        
class VPattern(object):
    """
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle 
    
    tracks -- list of VSnippet objects corresponding to the motif 
    """
    def __init__(self,original_pattern=None,
                 tracks=[]):
        self.original_pattern=original_pattern 
        self.tracks=tracks

        
class VAggregatedSeqlet(VPattern):
    """
    tracks is a list of Vsnippet objects -- corresponds to an aggregate motif 
    """
    def __init__(self,original_aggregated_seqlet=None,
                 tracks=[]):
        super(VAggregatedSeqlet,self).__init__(original_pattern=original_aggregated_seqlet,tracks=tracks)
         
class VSeqlet(VPattern):
    """
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle 
    tracks: list of VSnippet objects 
    """
    def __init__(self,
                 original_seqlet=None,
                 tracks=[],
                 coordinates=None):
        super(VSeqlet,self).__init__(tracks=tracks)
        self.coordinates=coordinates
        self.original_seqlet=original_seqlet 
        
class VSnippet(object):
    """
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle     
    """
    
    def __init__(self,track_name=None,
                 fwd_image=None,
                 rev_image=None):
        self.track_name=track_name
        self.fwd_image=load_image(fwd_image,dim="width=\"700px\"")
        self.rev_image=load_image(rev_image,dim="width=\"700px\"")

    
class VHistogram(object):
    """
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle 
    
    thresh: threshold (double) 
    num_above_thresh: number motifs passing threshold (integer) 
    """
    
    def __init__(self,image=None,
                 thresh=None,
                 num_above_thresh=None,
                 label=""):
        self.image=load_image(image,im_category=ImCategory.HISTOGRAM)
        self.thresh=thresh
        self.number_above_thresh=num_above_thresh
        self.label=label

        

class VTsne(object):
    """
    Inputs:
    image can be either a string to a png image file 
    or a matplotlib figure handle     
    cluster_id_to_color_triplet is a dictionary 
    """
    def __init__(self,image=None,
                 cluster_id_to_color_triplet={}):
        self.image=load_image(image)
        self.cluster_id_to_color_triplet=cluster_id_to_color_triplet

        
class VTsne_denoised(VTsne):
    def __init__(self,image=None,
                 cluster_id_to_color_triplet={},
                 num_pre_filtered=0,
                 num_post_filtered=0):
        super(VTsne_denoised,self).__init__(image,
                                            cluster_id_to_color_triplet)
        self.num_pre_filtered=num_pre_filtered
        self.num_post_filtered=num_post_filtered
    
#Converter methods for MODISCO classes
def convert_Snippet_to_VSnippet(snippet_instance,track_name=None):
        '''
        Converts and instance of the Snippet class into an instance of the VSnippet class for 
        HTML visualization 
        
        Optionally, provide a name for the track 
        '''
        #generate images
        fwd_image=plot_weights(snippet_instance.fwd)
        rev_image=plot_weights(snippet_instance.rev) 
        return VSnippet(track_name=track_name,
                        fwd_image=fwd_image,
                        rev_image=rev_image)

def create_VSnippet_list(pattern_instance):
        '''
        Creates a list of VSnippet objects for inclusion in tracks attribute of VPattern 
        and child classes of VPattern
        '''
        vsnippet_tracks=[] 
        for track_name in pattern_instance:
                cur_snippet=pattern_instance[track_name]
                cur_vsnippet=convert_Snippet_to_VSnippet(cur_snippet,track_name=track_name)
                vsnippet_tracks.append(cur_vsnippet)
        return vsnippet_tracks 
        
def convert_Pattern_to_VPattern(pattern_instance):
        '''
        Conversts an instance of the Pattern class to an instance of the VPattern class. 
        '''
        #create the VSnippet objects that compose the tracks
        vsnippet_tracks=create_VSnippet_list(pattern_instance)
        return VPattern(original_pattern=pattern_instance,
                        tracks=vsnippet_tracks)

def convert_Seqlet_to_VSeqlet(seqlet_instance):
        '''
        Converts an instance of the Seqlet class to an instance of the VSeqlet class. 
        '''
        #create the VSnippet objects that compose the tracks
        vsnippet_tracks=create_VSnippet_list(seqlet_instance)
        return VSeqlet(original_pattern=pattern_instance,
                        tracks=vsnippet_tracks)
        

def convert_AggregatedSeqlet_to_VAggregatedSeqlet(aggregated_seqlet_instance):
        '''
        Converts an instance of the AggregateSeqlet class to an instance of the VAggregatedSeqlet class. 
        '''
        aggregate_vsnippet_tracks=create_VSnippet_list(aggregated_seqlet_instance)
        return VAggregatedSeqlet(original_pattern=aggregated_seqlet_instance,
                                 tracks=aggregate_vsnippet_tracks)

def generate_VHistograms(seqlet_hist,seqlet_thresh,seqlet_number_above_thresh):
    '''
    generate a list of VHistogram objects (1 per task)
    using the outputs of core.MultiTaskSeqletCreation
    '''
    return [VHistogram(image=seqlet_hist[task],
                       thresh=seqlet_thresh[task],
                       num_above_thresh=seqlet_number_above_thresh[task],
                       label=task)
            for task in seqlet_hist.keys()]

        
def generate_VCluster(aggregated_seqlet_instance,n=5,tsne_embedding=None):
        '''
        generates a VCluster object from an AggregatedSeqlet object 
        n indicates how many sample seqlets to select (at random) from 
        SeqletsAndAlignments attribute of aggregated_seqlet_instance. 
        '''
        cur_VAggregatedSeqlet=convert_AggregatedSeqlet_to_VAggregatedSeqlet(aggregated_seqlet_instance)
        seqlets=aggregated_seqlet_instance.seqlets_and_alnmts.arr
        example_seqlets=[convert_Seqlet_to_VSeqlet(i) for i in np.random.choice(seqlets,n)]
        return Vcluster(tsne_embedding=tsne_embedding,
                        aggregate_motif=cur_VAggregatedSeqlet,
                        example_seqlets=example_seqlets)

def generate_VAllMetaclusterHeatmap(all_metaclusters_heatmap=None,
                                    all_metaclusters_data=None,
                                    meta_cluster_means=None,
                                    meta_cluster_sizes=None,
                                    num_meta_clusters=None):
    '''
    Generates VAllMetaclusterHeatmap object 
    '''
    cluster_id_to_mean={}
    cluster_id_to_num_seqlets_in_cluster={}
    for i in range(num_meta_clusters):
        cluster_id_to_mean[i]=meta_cluster_means[i]
        cluster_id_to_num_seqlets_in_cluster[i]=meta_cluster_sizes[i]
    return VAllMetaclusterHeatmap(image=all_metaclusters_heatmap,
                                  data=all_metaclusters_data,
                                  cluster_id_to_mean=cluster_id_to_mean,
                                  cluster_id_to_num_seqlets_in_cluster=cluster_id_to_num_seqlets_in_cluster)
