import sys
import os
_, path = sys.argv

parent = path.split('/')[:-1]
parent = '/'.join(parent)

outpath = parent + '/' + 'sup_on_'+path.split('/')[-1]
outpath = outpath.replace('.pkl','.yaml')
print "THEANO_FLAGS='device=gpu' train.py",outpath

if os.path.exists(outpath.replace('.yaml','.pkl')):
    print outpath.replace('.yaml', '.pkl')
    assert False

f = open(outpath, 'w')

f.write(
"""
!obj:pylearn2.train.Train {
    dataset:  &train !obj:pylearn2.datasets.mnist.MNIST {
        which_set: "train",
        #binarize: 1,
        one_hot: 1,
        start: 0,
        stop: 50000
    },
        model: !obj:galatea.dbm.inpaint.super_dbm.DBM_DropoutWrapper {
                        decapitate: 0,
                        super_dbm: !obj:galatea.dbm.inpaint.super_dbm.set_niter {
                                super_dbm: !pkl: "%(path)s",
                                niter: 6
                        },
    },
    algorithm: !obj:pylearn2.training_algorithms.sgd.SGD {
        momentum: .5,
        batch_size: 100,
        set_batch_size: 1,
        learning_rate: 1e-3,
        monitoring_dataset: {
            'train' : *train,
            'valid' : !obj:pylearn2.datasets.mnist.MNIST {
                                        which_set: "train",
                                        one_hot: 1,
                                        start: 50000,
                                        stop:  60000
                      },
            'test' : !obj:pylearn2.datasets.mnist.MNIST {
                                        which_set: "test",
                                        one_hot: 1,
                     }
            },
            cost : !obj:galatea.dbm.inpaint.super_dbm.DBM_DropoutWrapper_NLL {
                   },
            termination_criterion: !obj:pylearn2.termination_criteria.MonitorBased
            {
                        channel_name: "valid_err",
                        prop_decrease: .000,
                        N : 10
            }
        },
    extensions: [
                !obj:pylearn2.train_extensions.best_params.MonitorBasedSaveBest {
                        channel_name: "valid_err",
                        save_path: "${PYLEARN2_TRAIN_FILE_FULL_STEM}_best.pkl"
                }
        ],
    save_path: "${PYLEARN2_TRAIN_FILE_FULL_STEM}.pkl",
    save_freq : 1
}
""" % locals())

f.close()
print 'run train yourself, for some reason the subprocess was claiming a second gpu'
quit()
from pylearn2.utils.shell import run_shell_command
print 'shell will hide output until done, yay python'
out, rc = run_shell_command('train.py '+outpath)
print 'return code ',rc
print out
