import os
import signal
import deeplift
import numpy as np
import deeplift.backend as B
import theano
import theano.tensor.signal.conv
import h5py
import traceback


def create_detector_from_subset_of_sequential_layers(sequential_container,
                                                    idx_of_layer_of_interest,
                                                    channel_indices,
                                                    multipliers_on_channels):
    layers = []  
    #this adds in all the layers preceeding idx_of_layer_of_interest
    #(remember zero-based indexing...)
    for layer_idx in range(idx_of_layer_of_interest):
        layers.append(
         sequential_container.get_layers()[layer_idx].copy_blob_keep_params()
        )
    #add in the layer of interest, but with the channels subsetted to
    #the channels of interest
    layer_to_subset = sequential_container.get_layers()\
                       [idx_of_layer_of_interest]
    assert hasattr(layer_to_subset, "W"), "Layer does not have weights - "\
        +" make sure you have supplied the correct index for the conv layer?"
    subsetted_weights = layer_to_subset.W[channel_indices]
    subsetted_biases = layer_to_subset.b[channel_indices]
    layer_kwargs = layer_to_subset.get_yaml_compatible_object_kwargs()
    layer_kwargs['W'] = subsetted_weights 
    layer_kwargs['b'] = subsetted_biases
    subsetted_layer = layer_to_subset.\
                      load_blob_from_yaml_contents_only(**layer_kwargs)
    layers.append(subsetted_layer)
    #check if the next layer is an activation layer
    layer_after_layer_of_interest =\
      sequential_container.get_layers()[idx_of_layer_of_interest+1]
    if isinstance(layer_after_layer_of_interest, deeplift.blobs.Activation):
        layers.append(layer_after_layer_of_interest.copy_blob_keep_params())
    #multipliers_layer = sequential_container.get_layers()[layer_idx+1].copy_blob_keep_params()
    #add in a layer with a conv filter that is the multipliers
    #need to be reversed because this is doing a convolution, not cross corr
    multipliers_layer = deeplift.blobs.Conv2D(
                    name="multipliers_layer",
                    W=multipliers_on_channels[:,:,::-1,::-1].astype('float32'),
                    b=np.zeros(multipliers_on_channels.shape[0])\
                      .astype('float32'),
                    strides=(1,1), 
                    border_mode=B.BorderMode.valid)
    layers.append(multipliers_layer)
    deeplift.util.connect_list_of_layers(layers)
    layers[-1].build_fwd_pass_vars()
    model_to_return = deeplift.models.SequentialModel(layers=layers)
    model_to_return.get_layers()

    return model_to_return

def get_conv_out_symbolic_var(input_var,
                              set_of_2d_patterns_to_conv_with,
                              normalise_by_magnitude,
                              take_max):
    assert len(set_of_2d_patterns_to_conv_with.shape)==3
    if (normalise_by_magnitude):
        set_of_2d_patterns_to_conv_with =\
         set_of_2d_patterns_to_conv_with/\
          (np.sqrt(np.sum(np.sum(np.square(set_of_2d_patterns_to_conv_with),
                               axis=-1),
                        axis=-1))[:,None,None])
    filters = theano.tensor.as_tensor_variable(
               x=set_of_2d_patterns_to_conv_with,
               name="filters")
    conv_out = theano.tensor.signal.conv.conv2d(
                input=input_var,
                filters=filters)
    if (normalise_by_magnitude):
        sum_squares_per_pos =\
                   theano.tensor.signal.conv.conv2d(
                    input=theano.tensor.square(input_var),
                    filters=np.ones(set_of_2d_patterns_to_conv_with.shape)\
                            .astype("float32")) 
        per_pos_magnitude = theano.tensor.sqrt(sum_squares_per_pos)
        per_pos_magnitude += 0.0000001*(per_pos_magnitude < 0.0000001)
        conv_out = conv_out/per_pos_magnitude
    if (take_max):
        conv_out = theano.tensor.max(
                    theano.tensor.max(conv_out, axis=-1), #max over cols
                    axis=-1) #max over rows
    return conv_out 


def compile_conv_func_with_theano(set_of_2d_patterns_to_conv_with,
                                  normalise_by_magnitude=False,
                                  take_max=False):
    input_var = theano.tensor.TensorType(dtype=theano.config.floatX,
                                         broadcastable=[False]*3)("input")
    conv_out = get_conv_out_symbolic_var(input_var,
                                 set_of_2d_patterns_to_conv_with,
                                 normalise_by_magnitude=normalise_by_magnitude,
                                 take_max=take_max)
    func = theano.function([input_var],
                           conv_out,
                           allow_input_downcast=True)
    return func 


def get_max_cross_corr(filters, things_to_scan,
                           verbose=True, batch_size=10,
                           func_params_size=1000000,
                           progress_update=1000,
                           min_overlap=0.3):
    """
        func_params_size: when compiling functions
    """
    #reverse the patterns as the func is a conv not a cross corr
    filters = filters.astype("float32")[:,::-1,::-1]
    to_return = np.zeros((filters.shape[0], len(things_to_scan)))
    #compile the number of filters that result in a function with
    #params equal to func_params_size 
    params_per_filter = np.prod(filters[0].shape)
    filter_batch_size = int(func_params_size/params_per_filter)
    filter_length = filters.shape[-1]
    filter_idx = 0 
    while filter_idx < filters.shape[0]:
        print("On filters",filter_idx,"to",(filter_idx+filter_batch_size))
        filter_batch = filters[filter_idx:(filter_idx+filter_batch_size)]
        cross_corr_func = compile_conv_func_with_theano(
                           set_of_2d_patterns_to_conv_with=filter_batch,
                           normalise_by_magnitude=False,
                           take_max=True)  
        padding_amount = int((filter_length)*(1-min_overlap))
        padded_input = [np.pad(array=x,
                              pad_width=((padding_amount, padding_amount)),
                              mode="constant") for x in things_to_scan]
        max_cross_corrs = np.array(deeplift.util.run_function_in_batches(
                            func=cross_corr_func,
                            input_data_list=[padded_input],
                            batch_size=batch_size,
                            progress_update=(None if verbose==False else
                                             progress_update)))
        assert len(max_cross_corrs.shape)==2, max_cross_corrs.shape
        to_return[filter_idx:
                  (filter_idx+filter_batch_size),:] =\
                  np.transpose(max_cross_corrs)
        filter_idx += filter_batch_size
        
    return to_return


def get_top_N_scores_per_region(scores, N, exclude_hits_within_window):
    scores = scores.copy()
    assert len(scores.shape)==2, scores.shape
    if (N==1):
        return np.max(scores, axis=1)[:,None]
    else:
        top_n_scores = []
        for i in range(scores.shape[0]):
            top_n_scores_for_region=[]
            for n in range(N):
                max_idx = np.argmax(scores[i]) 
                top_n_scores_for_region.append(scores[i][max_idx])
                scores[i][max_idx-exclude_hits_within_window:
                          max_idx+exclude_hits_within_window-1] = -np.inf
            top_n_scores.append(top_n_scores_for_region) 
        return np.array(top_n_scores)
 

def jaccardify_dist_mat(dist_mat, verbose=True, power=1):
    if (verbose):
        print("calling jaccardify")
    dist_mat = np.power(dist_mat, power)
    import time
    t1 = time.time()
    minimum_sum = np.sum(np.minimum(dist_mat[:,None,:],
                         dist_mat[None,:,:]), axis=-1)
    maximum_sum = np.sum(np.maximum(dist_mat[:,None,:],
                         dist_mat[None,:,:]), axis=-1)
    ratio = minimum_sum/maximum_sum
    t2 = time.time()
    if (verbose):
        print("time taken in jaccardify",t2-t1)
    return ratio 


def compute_jaccardify(dist_mat, start_job, end_job):
    num_nodes = dist_mat.shape[0]
    distances = []
    for job_num in xrange(start_job, end_job):
        row_idx = int(job_num/num_nodes)
        col_idx = job_num%num_nodes
        minimum_sum = np.sum(np.minimum(dist_mat[row_idx,:],
                                        dist_mat[col_idx,:]))
        maximum_sum = np.sum(np.maximum(dist_mat[row_idx,:],
                                        dist_mat[col_idx,:]))
        ratio = minimum_sum/maximum_sum
        distances.append(ratio)
    return distances


#might be speed-upable further by recognizing that the distance is symmetric
def gpu_jaccardify(dist_mat, power=1,
                   func_params_size=1000000,
                   batch_size=100,
                   progress_update=1000,
                   verbose=True):
    if (power != 1):
        print("taking the power")
        dist_mat = np.power(dist_mat, power)
        print("took the power")
    num_nodes = dist_mat.shape[0]
    cols_batch_size = int(func_params_size/num_nodes) 
    print("cols_batch_size is",cols_batch_size)
    assert cols_batch_size > 0, "Please increase func_params_size; a single"+\
                                " col can't fit in the function otherwise"

    to_return = np.zeros(dist_mat.shape)

    col_idx = 0
    while col_idx < num_nodes:
        if (verbose):
            print("cols idx:",col_idx)
        #compile a function for computing distance to
        #nodes col_idx:(col_idx + cols_batch_size)

        #input var will store a batch of input data points
        input_var = theano.tensor.TensorType(
                        dtype=theano.config.floatX,
                        broadcastable=[False]*2)("input")
        
        end_col_idx = min(col_idx + cols_batch_size, num_nodes)
        minimum_sum = theano.tensor.sum(
                         theano.tensor.minimum(
                            input_var[:,None,:],
                            dist_mat[None,
                                     col_idx:end_col_idx,:]),
                                     axis=-1)
        maximum_sum = theano.tensor.sum(
                         theano.tensor.maximum(
                            input_var[:,None,:],
                            dist_mat[None,
                                     col_idx:end_col_idx,:]),
                                     axis=-1)
        ratios = minimum_sum/maximum_sum #the "jaccardified" distance

        #compile the function which takes input_var as the input tensor
        #and returns ratios 
        func = theano.function([input_var], ratios, allow_input_downcast=True)

        #apply the function in batches to all the nodes
        row_idx = 0
        while row_idx < num_nodes: 
            if (verbose):
                if (row_idx%progress_update == 0):
                    print("Done",row_idx)
            end_row_idx = row_idx+batch_size
            distances = func(dist_mat[row_idx:end_row_idx,:])
            to_return[row_idx:end_row_idx, col_idx:end_col_idx] = distances
            row_idx = end_row_idx
        col_idx = end_col_idx
    return to_return


#should be speed-upable further by recognizing that the distance is symmetric
def parallel_jaccardify(dist_mat, num_processes=4,
                        verbose=True, power=1,
                        temp_file_dir="tmp",
                        temp_file_prefix="jaccardify_h5"):

    if (os.path.isdir(temp_file_dir)==False):
        os.system("mkdir "+temp_file_dir)
    dist_mat = np.power(dist_mat, power)

    num_nodes = dist_mat.shape[0]
    total_tasks = num_nodes**2
    tasks_per_job = int(np.ceil(total_tasks/num_processes))

    launched_pids = []
    print(num_processes)
    for i in xrange(num_processes):
        pid = os.fork() 
        print(pid)
        if pid==0:
            try:
                #set a signal handler for interrupt signals
                signal.signal(signal.SIGINT,
                              (lambda signum, frame: os._exit(os.EX_TEMPFAIL)))
                start_job = tasks_per_job*i
                end_job = min(total_tasks, tasks_per_job*(i+1))
                distances = compute_jaccardify(dist_mat, start_job, end_job) 
                #write the distances to an h5 file
                h5_file_name = temp_file_dir+"/"\
                               +temp_file_prefix+"_"+str(i)+".h5"
                f = h5py.File(h5_file_name, "w")
                dset = f.create_dataset("/distances", data=distances)
                f.close()
                print("Exit!")
                os._exit(os.EX_OK) #exit the child
            except Exception, _:
                raise RuntimeError("Exception in job "+str(i)+\
                                   "\n"+traceback.format_exc()) 
                os._exit(os.EX_SOFTWARE)
        else:
            launched_pids.append(pid)

    try:
        while len(launched_pids) > 0:
            pid, return_code = os.wait()
            if return_code != os.EX_OK:  
                raise RuntimeError(
                "pid "+str(pid)+" gave error code "+str(return_code))
            if pid in launched_pids:
                launched_pids.remove(pid)

        #child processes would have all exited
        collated_distances = []
        #now collate all the stuff written to the various h5 files
        for i in xrange(num_processes):
            h5_file_name = temp_file_dir+"/"\
                           +temp_file_prefix+"_"+str(i)+".h5"
            f = h5py.File(h5_file_name)
            collated_distances.extend(f['/distances'])
            f.close()
            os.system("rm "+h5_file_name)
        assert len(collated_distances) == total_tasks 
        to_return = np.zeros((num_nodes, num_nodes))
        #now reshape the collated distances into a numpy array
        for i in xrange(len(collated_distances)):
            row_idx = int(i/num_nodes)
            col_idx = i%num_nodes
            to_return[row_idx, col_idx] = collated_distances[i]
        return to_return
    except KeyboardInterrupt, OSError:
        for pid in launched_pids:
            try:
                os.kill(pid, signal.SIGHUP)
            except:
                pass
        raise


def make_graph_from_dist_mat(dist_mat):
    import networkx as nx
    G = nx.Graph()
    print("Adding nodes")
    for i in range(len(dist_mat)):
        G.add_node(i)
    print("nodes added")
    edges_to_add = []
    print("Preparing edges")
    for i in range(len(dist_mat)):
        for j in range(i+1,len(dist_mat)):
            edges_to_add.append((i,j,{'weight':dist_mat[i,j]})) 
    print("Done preparing edges")
    G.add_edges_from(edges_to_add)
    print("Done adding edges")
    return G


def cluster_louvain(dist_mat):
    import community
    graph = make_graph_from_dist_mat(dist_mat)
    print("making partition")
    partition = community.best_partition(graph)
    print("done making partition")
    louvain_labels = [partition[i] for i in range(len(partition.keys()))]
    return louvain_labels


def scan_regions_with_filters(filters, regions_to_scan,
                              batch_size=50, progress_update=1000):
    """
        filters: for PWMs, use log-odds matrices.
        Will be cross-correlated with sequence
    
        set_of_regions: either one-hot-encoded or deeplift score tracks.
    """ 
    if (len(filters.shape)==3):
        filters = filters[:,None,:,:]
    assert filters.shape[1]==1 #input channels=1
    assert filters.shape[2]==4 #acgt
    assert len(regions_to_scan.shape)==4
    assert regions_to_scan.shape[1]==1 #input channels=1
    assert regions_to_scan.shape[2]==4 #acgt

    #set up the theano convolution 
    fwd_filters = filters[:,:,::-1,::-1] #convolutions reverse things
    rev_comp_filters = filters

    input_var = theano.tensor.TensorType(dtype=theano.config.floatX,
                                         broadcastable=[False]*4)("input") 
    fwd_filters_var = theano.tensor.as_tensor_variable(
                        x=fwd_filters, name="fwd_filters")
    rev_comp_filters_var = theano.tensor.as_tensor_variable(
                             x=rev_comp_filters, name="rev_comp_filters")
    fwd_conv_out = theano.tensor.nnet.conv2d(
                    input=input_var, filters=fwd_filters_var)
    rev_comp_conv_out = theano.tensor.nnet.conv2d(
                         input=input_var, filters=rev_comp_filters_var)

    #concatenate the results to take an elementwise max
    #remember that the lenght of the row dimension is 1, so this is a
    #good dimension to take advantage of for concatenation
    concatenated_fwd_and_rev_results = theano.tensor.concatenate(
        [fwd_conv_out, rev_comp_conv_out], axis=2) 

    fwd_or_rev = theano.tensor.argmax(concatenated_fwd_and_rev_results, axis=2, keepdims=True)
    scores = theano.tensor.max(concatenated_fwd_and_rev_results, axis=2, keepdims=True)

    #concatenated score and complementation
    concatenated_score_and_orientation = theano.tensor.concatenate(
        [scores,fwd_or_rev], axis=2)

    compiled_func = theano.function([input_var],
                                    concatenated_score_and_orientation,
                                    allow_input_downcast=True)

    #run function in batches
    conv_results = np.array(deeplift.util.run_function_in_batches(
                            func=compiled_func,
                            input_data_list=[regions_to_scan],
                            batch_size=batch_size,
                            progress_update=progress_update))

    return conv_results
