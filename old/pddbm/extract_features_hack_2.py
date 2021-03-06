import copy
import os
import warnings
import time
from pylearn2.config import yaml_parse
import numpy as np
from theano import config
from theano import tensor as T
#from theano.sandbox.neighbours import images2neibs
from theano import function
from pylearn2.datasets.preprocessing import ExtractPatches, ExtractGridPatches, ReassembleGridPatches
from pylearn2.utils import serial
from pylearn2.datasets.dense_design_matrix import DenseDesignMatrix, DefaultViewConverter
from pylearn2.datasets.cifar10 import CIFAR10
from pylearn2.datasets.cifar100 import CIFAR100
from pylearn2.datasets.tl_challenge import TL_Challenge
import sys
config.floatX = 'float32'

class halver:
    def __init__(self,f,nhid):
        self.f = f
        self.nhid = nhid

    def __call__(self,X):
        m = X.shape[0]
        #mid = m/2
        m1 = m/3
        m2 = 2*m/3

        rval = np.zeros((m,self.nhid),dtype='float32')
        rval[0:m1,:] = self.f(X[0:m1,:])
        rval[m1:m2,:] = self.f(X[m1:m2,:])
        rval[m2:,:] = self.f(X[m2:,:])

        return rval


class FeaturesDataset:
    def __init__(self, dataset_maker, num_examples, pipeline_path):
        """
            dataset_maker: A callable that returns a Dataset
            num_examples: the number of examples we expect the dataset to have
                          (just for error checking purposes)
        """
        self.dataset_maker = dataset_maker
        self.num_examples = num_examples
        self.pipeline_path = pipeline_path


stl10 = {}
stl10_no_shelling = {}
stl10_size = { 'train' : 5000, 'test' : 8000 }

cifar10 = {}
cifar10_size = { 'train' : 50000, 'test' : 10000 }

cifar100 = {}
cifar100_size = { 'train' : 50000, 'test' : 10000 }

tl_challenge = {}
tl_challenge_size = { 'train' : 120, 'test' : 0 }

class dataset_loader:
    def __init__(self, path):
        self.path = path

    def __call__(self):
        return serial.load(self.path)

class dataset_constructor:
    def __init__(self, cls, which_set):
        self.cls = cls
        self.which_set = which_set

    def __call__(self):
        return self.cls(self.which_set)


for which_set in ['train', 'test']:
    stl10[which_set] = {}
    stl10_no_shelling[which_set] = {}
    cifar10[which_set] = {}
    cifar100[which_set] = {}
    tl_challenge[which_set] = {}

    #this is for patch size, not datset size
    for size in [6]:
        stl10[which_set][size] = FeaturesDataset( dataset_maker = dataset_loader( '${PYLEARN2_DATA_PATH}/stl10/stl10_32x32/'+which_set+'.pkl'),
                                            num_examples = stl10_size[which_set],
                                            pipeline_path = '${PYLEARN2_DATA_PATH}/stl10/stl10_patches/preprocessor.pkl')

        stl10_no_shelling[which_set][size] = FeaturesDataset( dataset_maker = dataset_loader( '${PYLEARN2_DATA_PATH}/stl10/stl10_32x32/'+which_set+'.pkl'),
                                            num_examples = stl10_size[which_set],
                                            pipeline_path = '${GOODFELI_TMP}/stl10/stl10_patches_no_shelling/preprocessor.pkl')

        cifar10[which_set][size] = FeaturesDataset( dataset_maker = dataset_constructor( CIFAR10, which_set),
                                                num_examples = cifar10_size[which_set],
                                                pipeline_path = '${GOODFELI_TMP}/cifar10_preprocessed_pipeline_2M_6x6.pkl')

        cifar100[which_set][size] = FeaturesDataset( dataset_maker = dataset_constructor( CIFAR100, which_set),
                                                num_examples = cifar100_size[which_set],
                                                pipeline_path = '${PYLEARN2_DATA_PATH}/cifar100/cifar100_patches/preprocessor.pkl')

        tl_challenge[which_set][size] = FeaturesDataset( dataset_maker = dataset_constructor( TL_Challenge, which_set),
                                                num_examples = tl_challenge_size[which_set],
                                                pipeline_path = '${GOODFELI_TMP}/tl_challenge_patches_2M_6x6_prepro.pkl')


    stl10[which_set][8] = FeaturesDataset( dataset_maker = dataset_loader( '${PYLEARN2_DATA_PATH}/stl10/stl10_32x32/'+which_set+'.pkl'),
                                            num_examples = stl10_size[which_set],
                                            pipeline_path = '${PYLEARN2_DATA_PATH}/stl10/stl10_patches_8x8/preprocessor.pkl')

    cifar100[which_set][8] = FeaturesDataset( dataset_maker = dataset_constructor( CIFAR100, which_set),
                                                num_examples = cifar100_size[which_set],
                                                pipeline_path = '${PYLEARN2_DATA_PATH}/cifar100/cifar100_patches_8x8/preprocessor.pkl')


class FeatureExtractor:
    def __init__(self, batch_size, model_path, pooling_region_counts,
           save_paths, feature_type, dataset_family, which_set,
         pool_mode = 'mean'):

        self.batch_size = batch_size
        self.model_path = model_path

        assert len(pooling_region_counts) == len(save_paths)

        self.pooling_region_counts = pooling_region_counts
        self.save_paths = save_paths
        self.feature_type = feature_type
        self.which_set = which_set
        self.dataset_family = dataset_family
        self.pool_mode = pool_mode

    def __call__(self):

        print 'loading model'
        model_path = self.model_path
        self.model = serial.load(model_path)
        self.model.make_pseudoparams()
        self.model.set_dtype('float32')
        self.size = int(np.sqrt(self.model.nvis/3))

        self._execute()

    def _execute(self):

        batch_size = self.batch_size
        feature_type = self.feature_type
        pooling_region_counts = self.pooling_region_counts
        dataset_family = self.dataset_family
        which_set = self.which_set
        model = self.model
        size = self.size

        nan = 0


        dataset_descriptor = dataset_family[which_set][size]

        dataset = dataset_descriptor.dataset_maker()
        expected_num_examples = dataset_descriptor.num_examples

        full_X = dataset.get_design_matrix()
        assert full_X.dtype == 'float32'
        num_examples = full_X.shape[0]
        assert num_examples == expected_num_examples

        print 'restricting to examples from classes 0 and 1'
        full_X = full_X[dataset.y_fine < 2, :]

        #update for after restriction
        num_examples = full_X.shape[0]

        assert num_examples > 0

        dataset.X = None
        dataset.design_loc = None
        dataset.compress = False

        patchifier = ExtractGridPatches( patch_shape = (size,size), patch_stride = (1,1) )

        pipeline = serial.load(dataset_descriptor.pipeline_path)

        assert isinstance(pipeline.items[0], ExtractPatches)
        pipeline.items[0] = patchifier


        print 'defining features'
        V = T.matrix('V')
        assert V.type.dtype == 'float32'
        model.make_pseudoparams()
        d = model.infer(V = V)

        H = d['H_hat']
        Mu1 = d['S_hat']
        G = d['G_hat']
        if len(G) != 1:
            raise NotImplementedError("only supports two layer pd-dbms for now")
        G ,= G

        assert H.dtype == 'float32'
        assert Mu1.dtype == 'float32'

        nfeat = model.s3c.nhid + model.dbm.rbms[0].nhid

        if self.feature_type == 'map_hs':
            feat = (H > 0.5) * Mu1
            raise NotImplementedError("doesn't support layer 2")
        elif self.feature_type == 'map_h':
            feat = T.cast(H > 0.5, dtype='float32')
            raise NotImplementedError("doesn't support layer 2")
        elif self.feature_type == 'exp_hs':
            feat = H * Mu1
            raise NotImplementedError("doesn't support layer 2")
        elif self.feature_type == 'exp_hs_split':
            Z = H * Mu1
            pos = T.clip(Z,0.,1e32)
            neg = T.clip(-Z,0,1e32)
            feat = T.concatenate((pos,neg),axis=1)
            nfeat *= 2
            raise NotImplementedError("doesn't support layer 2")
        elif self.feature_type == 'exp_h,exp_g':
            feat = T.concatenate((H,G),axis=1)
        elif self.feature_type == 'exp_h_thresh':
            feat = H * (H > .01)
            raise NotImplementedError("doesn't support layer 2")
        else:
            raise NotImplementedError()



        assert feat.dtype == 'float32'
        print 'compiling theano function'
        f = function([V],feat)

        if config.device.startswith('gpu') and nfeat >= 4000:
            f = halver(f, nfeat)

        topo_feat_var = T.TensorType(broadcastable = (False,False,False,False), dtype='float32')()
        if self.pool_mode == 'mean':
            region_feat_var = topo_feat_var.mean(axis=(1,2))
        elif self.pool_mode == 'max':
            region_feat_var = topo_feat_var.max(axis=(1,2))
        else:
            raise ValueError("Unknown pool mode: "+self.pool_mode)
        region_features = function([topo_feat_var],
                region_feat_var )

        def average_pool( stride ):
            def point( p ):
                return p * ns / stride

            rval = np.zeros( (topo_feat.shape[0], stride, stride, topo_feat.shape[3] ) , dtype = 'float32')

            for i in xrange(stride):
                for j in xrange(stride):
                    rval[:,i,j,:] = region_features( topo_feat[:,point(i):point(i+1), point(j):point(j+1),:] )

            return rval

        outputs = [ np.zeros((num_examples,count,count,nfeat),dtype='float32') for count in pooling_region_counts ]

        assert len(outputs) > 0

        fd = DenseDesignMatrix(X = np.zeros((1,1),dtype='float32'), view_converter = DefaultViewConverter([1, 1, nfeat] ) )

        ns = 32 - size + 1
        depatchifier = ReassembleGridPatches( orig_shape  = (ns, ns), patch_shape=(1,1) )

        if len(range(0,num_examples-batch_size+1,batch_size)) <= 0:
            print num_examples
            print batch_size

        for i in xrange(0,num_examples-batch_size+1,batch_size):
            print i
            t1 = time.time()

            d = copy.copy(dataset)
            d.set_design_matrix(full_X[i:i+batch_size,:])

            t2 = time.time()

            #print '\tapplying preprocessor'
            d.apply_preprocessor(pipeline, can_fit = False)
            X2 = np.cast['float32'](d.get_design_matrix())

            t3 = time.time()

            #print '\trunning theano function'
            feat = f(X2)

            t4 = time.time()

            assert feat.dtype == 'float32'

            feat_dataset = copy.copy(fd)

            if np.any(np.isnan(feat)):
                nan += np.isnan(feat).sum()
                feat[np.isnan(feat)] = 0

            feat_dataset.set_design_matrix(feat)

            #print '\treassembling features'
            feat_dataset.apply_preprocessor(depatchifier)

            #print '\tmaking topological view'
            topo_feat = feat_dataset.get_topological_view()
            assert topo_feat.shape[0] == batch_size

            t5 = time.time()

            #average pooling
            for output, count in zip(outputs, pooling_region_counts):
                output[i:i+batch_size,...] = average_pool(count)

            t6 = time.time()

            print (t6-t1, t2-t1, t3-t2, t4-t3, t5-t4, t6-t5)

        for output, save_path in zip(outputs, self.save_paths):
            np.save(save_path,output)


        if nan > 0:
            warnings.warn(str(nan)+' features were nan')

if __name__ == '__main__':
    assert len(sys.argv) == 2
    yaml_path = sys.argv[1]

    assert yaml_path.endswith('.yaml')
    val = yaml_path[0:-len('.yaml')]
    os.environ['FEATURE_EXTRACTOR_YAML_PATH'] = val
    os.putenv('FEATURE_EXTRACTOR_YAML_PATH',val)

    extractor = yaml_parse.load_path(yaml_path)

    extractor()
