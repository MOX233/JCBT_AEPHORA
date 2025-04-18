import os # Configure which GPU
if os.getenv("CUDA_VISIBLE_DEVICES") is None:
    gpu_num = 2 # Use "" to use the CPU
    os.environ["CUDA_VISIBLE_DEVICES"] = f"{gpu_num}"
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import sionna
import tensorflow as tf
import matplotlib.pyplot as plt
import numpy as np
import pickle
import time
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        tf.config.experimental.set_memory_growth(gpus[0], True)
    except RuntimeError as e:
        print(e)

# Avoid warnings from TensorFlow
tf.get_logger().setLevel('ERROR')

# Set random seed for reproducibility
sionna.config.seed = 42

# Import Sionna RT components
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, Camera

# For link-level simulations
from sionna.channel import cir_to_ofdm_channel, subcarrier_frequencies, OFDMChannel, ApplyOFDMChannel, CIRDataset
from sionna.nr import PUSCHConfig, PUSCHTransmitter, PUSCHReceiver
from sionna.utils import compute_ber, ebnodb2no, PlotBER
from sionna.ofdm import KBestDetector, LinearDetector
from sionna.mimo import StreamManagement

from utils.options import args_parser
from utils.sumo_utils import read_trajectoryInfo_timeindex

# 设置参数
N_t_H = 1  
N_t_V = 64  

N_r_H = 1   
N_r_V = 8   


args = args_parser()
args.trajectoryInfo_path = './sumo_data/trajectory_Lbd0.10.csv'
start_time=700
end_time=800
frequency = 28e9 # 5.9e9
pattern = "iso" # "tr38901"
h_rx = 3
h_tx = 30

trajectoryInfo = read_trajectoryInfo_timeindex(
    args,
    start_time=start_time,
    end_time=end_time,
    display_intervel=0.05,
)
channel_gains_list = []
#for scene_time in 500+0.1*np.array(list(range(10))):
for scene_time in trajectoryInfo.keys():
    _time = time.time()
    scene = sionna.rt.load_scene('scene_from_sionna.xml')
    # scene = sionna.rt.load_scene('scene_NoBuildings.xml')
    car_positions = []
    car_velocities = []
    rx_positions = []
    rx_velocities = []
    
    for i,v in enumerate(trajectoryInfo[scene_time].values()):
        car = scene.get(f'Car.{i+1}')
        x, y = v['pos']
        v, angle = v['v'], v['angle']
        v_x, v_y = v*np.cos(angle), v*np.sin(angle)
        
        car.position = [x, y, 1.4]
        car.velocity = [v_x, v_y, 0]
        
        #car.orientation = [np.pi/2, 0, 0] #!!!!!bug
        car_positions.append(car.position)
        car_velocities.append(car.velocity)
        rx_positions.append([x,y,h_rx])
        rx_velocities.append(car.velocity)
        
        
    # car = scene.get('Car.1')
    # car.position = [250,-250,1.4]
    # car.look_at([car.position[0]+np.cos(theta),car.position[1]+np.sin(theta),car.position[2]])
    #new_orientation = (np.pi/2, 0,  0)
    #car.orientation = type(car.orientation)(new_orientation)
    #car.orientation = type(car.orientation)(new_orientation, device=car.orientation.device)
    #car.orientation = [0,0,0]

    # Configure antenna array for all transmitters
    scene.tx_array = PlanarArray(num_rows=N_t_H,
                                num_cols=N_t_V,
                                vertical_spacing=0.5,
                                horizontal_spacing=0.5,
                                pattern=pattern,
                                polarization="V")

    # Configure antenna array for all receivers
    scene.rx_array = PlanarArray(num_rows=N_r_H,
                                num_cols=N_r_V,
                                vertical_spacing=0.5,
                                horizontal_spacing=0.5,
                                pattern=pattern,
                                polarization="V")

    # Create transmitter
    tx1 = Transmitter(name="tx_1",
                    position=[300,300,h_tx])
    tx2 = Transmitter(name="tx_2",
                    position=[-300,300,h_tx])
    tx3 = Transmitter(name="tx_3",
                    position=[300,-300,h_tx])
    tx4 = Transmitter(name="tx_4",
                    position=[-300,-300,h_tx])
    tx1.look_at([0,0,0])
    tx2.look_at([0,0,0])
    tx3.look_at([0,0,0])
    tx4.look_at([0,0,0])
    
    # Add transmitter instance to scene
    scene.add(tx1)
    scene.add(tx2)
    scene.add(tx3)
    scene.add(tx4)

    # Create a receiver
    for i,v in enumerate(trajectoryInfo[scene_time].values()):
        rx = Receiver(name=f"rx_{i+1}",
                    position=rx_positions[i],
                    orientation=[0,0,0])
        
        # Add receiver instance to scene
        scene.add(rx)

    # tx.look_at(rx) # Transmitter points towards receiver

    scene.frequency = frequency # in Hz; implicitly updates RadioMaterials

    scene.synthetic_array = True # If set to False, ray tracing will be done per antenna element (slower for large arrays)

    Road_horizontal1 = scene.get('Road_horizontal1')
    Road_horizontal1.radio_material = 'itu_concrete'
    Road_horizontal2 = scene.get('Road_horizontal2')
    Road_horizontal2.radio_material = 'itu_concrete'
    Road_vertical1 = scene.get('Road_vertical1')
    Road_vertical1.radio_material = 'itu_concrete'
    Road_vertical2 = scene.get('Road_vertical2')
    Road_vertical2.radio_material = 'itu_concrete'

    # Compute propagation paths
    paths = scene.compute_paths(max_depth=5,
                                num_samples=1e6)  # Number of rays shot into directions defined
                                                # by a Fibonacci sphere , too few rays can
                                                # lead to missing paths

    # Show the coordinates of the starting points of all rays.
    # These coincide with the location of the transmitters.
    # print("Source coordinates: ", paths.sources.numpy())
    # print("Transmitter coordinates: ", list(scene.transmitters.values())[0].position.numpy())

    # Show the coordinates of the endpoints of all rays.
    # These coincide with the location of the receivers.
    # print("Target coordinates: ",paths.targets.numpy())
    # print("Receiver coordinates: ",list(scene.receivers.values())[0].position.numpy())

    # Show the types of all paths:
    # 0 - LoS, 1 - Reflected, 2 - Diffracted, 3 - Scattered
    # Note that Diffraction and scattering are turned off by default.
    # print("Path types: ", paths.types.numpy())

    # We can now access for every path the channel coefficient, the propagation delay,
    # as well as the angles of departure and arrival, respectively (zenith and azimuth).

    # Let us inspect a specific path in detail
    # path_idx = 0 # Try out other values in the range [0, 13]
    # For a detailed overview of the dimensions of all properties, have a look at the API documentation
    # print(f"\n--- Detailed results for path {path_idx} ---")
    # print(f"Channel coefficient: {paths.a[0,0,0,0,0,path_idx, 0].numpy()}")
    # print(f"Propagation delay: {paths.tau[0,0,0,path_idx].numpy()*1e6:.5f} us")
    # print(f"Zenith angle of departure: {paths.theta_t[0,0,0,path_idx]:.4f} rad")
    # print(f"Azimuth angle of departure: {paths.phi_t[0,0,0,path_idx]:.4f} rad")
    # print(f"Zenith angle of arrival: {paths.theta_r[0,0,0,path_idx]:.4f} rad")
    # print(f"Azimuth angle of arrival: {paths.phi_r[0,0,0,path_idx]:.4f} rad")

    paths_dict = paths.to_dict()
    
    #import ipdb;ipdb.set_trace()
    
    [batch_size, num_rx, num_rx_ant, num_tx, num_tx_ant, max_num_paths, num_time_steps] = paths_dict['a'].shape
    # print('batch_size=', batch_size)
    # print('num_rx=', num_rx)
    # print('num_rx_ant=',num_rx_ant)
    # print('num_tx=', num_tx)
    # print('num_tx_ant=', num_tx_ant)
    # print('max_num_paths=', max_num_paths)
    # print('num_time_steps=', num_time_steps)

    from sionna.ofdm import ResourceGrid
    rg = ResourceGrid(num_ofdm_symbols=1024,
                    fft_size=1024,
                    subcarrier_spacing=30e3)

    # delay_resolution = rg.ofdm_symbol_duration/rg.fft_size
    # print("Delay   resolution (ns): ", int(delay_resolution/1e-9))

    # doppler_resolution = rg.subcarrier_spacing/rg.num_ofdm_symbols
    # print("Doppler resolution (Hz): ", int(doppler_resolution))

    a = paths_dict['a']
    tau = paths_dict['tau']
    frequencies = tf.ones([1]) * scene.frequency
    # frequencies = subcarrier_frequencies(rg.fft_size, rg.subcarrier_spacing)
    channel_gains = cir_to_ofdm_channel(frequencies,a,tau)[0,:,:,:,:,0,0]
    # channel_gains = cir_to_ofdm_channel(frequencies,a,tau)
    channel_gains_list.append(channel_gains)
    
    for i,k in enumerate(trajectoryInfo[scene_time].keys()):
        trajectoryInfo[scene_time][k]['h'] = channel_gains[i,:,:].numpy()

    del scene
    print('loaded scene_time=',scene_time, ' process time=',time.time()-_time, ' s')
# 保存文件
with open(f"./sionna_result/trajectoryInfo_{start_time}_{end_time}_3Dbeam_tx({N_t_H},{N_t_V})_rx({N_r_H},{N_r_V})_freq{frequency:.1e}.pkl", "wb") as tf:
    pickle.dump(trajectoryInfo,tf)

# import ipdb;ipdb.set_trace()


# new_orientation = (np.pi, 0,  0)
# car.orientation = type(car.orientation)(new_orientation, device=car.orientation.device)