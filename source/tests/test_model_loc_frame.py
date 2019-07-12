import dpdata,os,sys,json,unittest
import numpy as np
import tensorflow as tf
from common import Data

lib_path = os.path.dirname(os.path.realpath(__file__)) + ".."
sys.path.append (lib_path)

from deepmd.RunOptions import RunOptions
from deepmd.DataSystem import DataSystem
from deepmd.DescrptLocFrame import DescrptLocFrame
from deepmd.EnerFitting import EnerFitting
from deepmd.Model import Model
from deepmd.common import j_must_have, j_must_have_d, j_have

global_ener_float_precision = tf.float64
global_tf_float_precision = tf.float64
global_np_float_precision = np.float64

def gen_data() :
    tmpdata = Data(rand_pert = 0.1, seed = 1)
    sys = dpdata.LabeledSystem()
    sys.data['coords'] = tmpdata.coord
    sys.data['atom_types'] = tmpdata.atype
    sys.data['cells'] = tmpdata.cell
    nframes = tmpdata.nframes
    natoms = tmpdata.natoms
    sys.data['coords'] = sys.data['coords'].reshape([nframes,natoms,3])
    sys.data['cells'] = sys.data['cells'].reshape([nframes,3,3])
    sys.data['energies'] = np.zeros([nframes,1])
    sys.data['forces'] = np.zeros([nframes,natoms,3])
    sys.data['virials'] = []
    sys.to_deepmd_npy('system', prec=np.float64)    

class TestModel(unittest.TestCase):
    def setUp(self) :
        gen_data()

    def test_model(self):
        jfile = 'water.json'
        with open(jfile) as fp:
            jdata = json.load (fp)
        run_opt = RunOptions(None) 
        systems = j_must_have(jdata, 'systems')
        set_pfx = j_must_have(jdata, 'set_prefix')
        batch_size = j_must_have(jdata, 'batch_size')
        test_size = j_must_have(jdata, 'numb_test')
        batch_size = 1
        test_size = 1
        stop_batch = j_must_have(jdata, 'stop_batch')
        rcut = j_must_have (jdata['model']['descriptor'], 'rcut')
        
        data = DataSystem(systems, set_pfx, batch_size, test_size, rcut, run_opt = None)
        
        test_prop_c, \
            test_energy, test_force, test_virial, test_atom_ener, \
            test_coord, test_box, test_type, test_fparam, \
            natoms_vec, \
            default_mesh \
            = data.get_test ()
        numb_test = 1
        
        bias_atom_e = data.compute_energy_shift()

        descrpt = DescrptLocFrame(jdata['model']['descriptor'])
        fitting = EnerFitting(jdata['model']['fitting_net'], descrpt)
        model = Model(jdata['model'], descrpt, fitting)

        davg, dstd = model.compute_dstats([test_coord], [test_box], [test_type], [natoms_vec], [default_mesh])

        t_prop_c           = tf.placeholder(tf.float32, [4],    name='t_prop_c')
        t_energy           = tf.placeholder(global_ener_float_precision, [None], name='t_energy')
        t_force            = tf.placeholder(global_tf_float_precision, [None], name='t_force')
        t_virial           = tf.placeholder(global_tf_float_precision, [None], name='t_virial')
        t_atom_ener        = tf.placeholder(global_tf_float_precision, [None], name='t_atom_ener')
        t_coord            = tf.placeholder(global_tf_float_precision, [None], name='i_coord')
        t_type             = tf.placeholder(tf.int32,   [None], name='i_type')
        t_natoms           = tf.placeholder(tf.int32,   [model.ntypes+2], name='i_natoms')
        t_box              = tf.placeholder(global_tf_float_precision, [None, 9], name='i_box')
        t_mesh             = tf.placeholder(tf.int32,   [None], name='i_mesh')
        is_training        = tf.placeholder(tf.bool)
        t_fparam = None

        energy, force, virial, atom_ener, atom_virial \
            = model.build (t_coord, 
                           t_type, 
                           t_natoms, 
                           t_box, 
                           t_mesh,
                           t_fparam,
                           davg = davg,
                           dstd = dstd,
                           bias_atom_e = bias_atom_e, 
                           suffix = "loc_frame", 
                           reuse = False)

        feed_dict_test = {t_prop_c:        test_prop_c,
                          t_energy:        test_energy              [:numb_test],
                          t_force:         np.reshape(test_force    [:numb_test, :], [-1]),
                          t_virial:        np.reshape(test_virial   [:numb_test, :], [-1]),
                          t_atom_ener:     np.reshape(test_atom_ener[:numb_test, :], [-1]),
                          t_coord:         np.reshape(test_coord    [:numb_test, :], [-1]),
                          t_box:           test_box                 [:numb_test, :],
                          t_type:          np.reshape(test_type     [:numb_test, :], [-1]),
                          t_natoms:        natoms_vec,
                          t_mesh:          default_mesh,
                          is_training:     False}

        sess = tf.Session()
        sess.run(tf.global_variables_initializer())
        [e, f, v] = sess.run([energy, force, virial], 
                             feed_dict = feed_dict_test)

        e = e.reshape([-1])
        f = f.reshape([-1])
        v = v.reshape([-1])
        refe = [1.165945032784766511e+01]
        reff = [2.356319331246305437e-01,1.772322096063349284e-01,1.455439548950788684e-02,1.968599426000810226e-01,2.648214484898352983e-01,7.595232354012236564e-02,-2.121321856338151401e-01,-2.463886119018566037e-03,-2.075636300914874069e-02,-9.360310077571798101e-03,-1.751965198776750943e-01,-2.046405309983102827e-02,-1.990194093283037535e-01,-1.828347741191920298e-02,-6.916374506995154325e-02,-1.197997068502068031e-02,-2.461097746875573200e-01,1.987744214930105627e-02]
        refv = [-4.998509978510510265e-01,-1.966169437179327711e-02,1.136130543869883977e-02,-1.966169437179334650e-02,-4.575353297894450555e-01,-2.668666556859019493e-03,1.136130543869887100e-02,-2.668666556859039876e-03,2.455466940358383508e-03]
        refe = np.reshape(refe, [-1])
        reff = np.reshape(reff, [-1])
        refv = np.reshape(refv, [-1])

        places = 10
        for ii in range(e.size) :
            self.assertAlmostEqual(e[ii], refe[ii], places = places)
        for ii in range(f.size) :
            self.assertAlmostEqual(f[ii], reff[ii], places = places)
        for ii in range(v.size) :
            self.assertAlmostEqual(v[ii], refv[ii], places = places)

