import numpy as N
from theano import function, shared
import theano.tensor as T

class TanhFeatureExtractor:
    def __init__(self, W, b):
        self.W = shared(W)
        self.b = shared(b)
        self.redo_theano()

    def redo_theano(self):
        X = T.matrix()
        H = self(X)
        self.extract = function([X],H)

        #number examples x number hiddens x number visibles
        J = (1.-T.sqr(H)).dimshuffle(0,1,'x') * self.W.dimshuffle('x',1,0)
        self.jacobian_of_expand = function([X],J)
    #

    def __call__(self, X):
        return T.tanh(T.dot(X, self.W)+self.b)
    #

    @classmethod
    def make_from_examples(cls, X, low, high, directed = True):
        #for every pair of examples (i,j)
        #make a feature that takes on the value low at i
        #and value high at j
        #if directed, order of (i,j) matters, otherwise it does not


        m,n =  X.shape

        if directed:
            h = m **2 - m
        else:
            h = m * (m-1)/2
        W = N.zeros((n,h))
        b = N.zeros(h)
        idx = 0

        inv_low = N.arctanh(low)
        if N.abs(N.tanh(inv_low)-low) > 1e-6:
            assert False
        #

        inv_high = N.arctanh(high)

        for i in xrange(X.shape[0]):
            if directed:
                r = xrange(m)
            else:
                r = xrange(i+1,m)

            for j in r:
                if i == j:
                    continue

                diff = X[j,:] - X[i,:]
                direction = diff / N.sqrt(N.square(diff).sum())
                pi = N.dot(X[i,:],direction)
                pj = N.dot(X[j,:],direction)

                wmag =  (inv_high - inv_low) / (pj - pi)

                b[idx] = (pj*inv_low - pi*inv_high) / (pj - pi)
                W[:,idx] = wmag * direction

                #check it
                ival = N.tanh(N.dot(W[:,idx],X[i,:])+b[idx])
                jval = N.tanh(N.dot(W[:,idx],X[j,:])+b[idx])


                assert abs(ival-low) < 1e-6
                assert abs(jval-high) < 1e-6

                idx += 1

        assert idx == h


        return TanhFeatureExtractor(W,b)
