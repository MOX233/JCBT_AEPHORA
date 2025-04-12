import os # Configure which GPU
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import matplotlib.pyplot as plt
import numpy as np
import pickle
import time
import random
import torch

from utils.NN_utils import BestGainPredictionModel, train_gainpred_model, train_gainlevelpred_model
from utils.options import args_parser
from utils.mox_utils import setup_seed, get_save_dirs, split_string, save_log, np2torch
from utils.plot_utils import plot_gainlevelpred
from utils.data_utils import get_prepared_dataset, prepare_dataset

if __name__ == "__main__":
    # 设置随机数种子
    setup_seed(20)

    # freq = 5.9e9
    # DS_start, DS_end = 500, 700
    freq = 28e9
    DS_start, DS_end = 300, 700
    preprocess_mode = 2
    n_pilot = 16
    M_r, N_bs, M_t = 8, 4, 64
    P_t = 1e-1
    P_noise = 1e-14
    gpu = 6
    device = f'cuda:{gpu}' if torch.cuda.is_available() else 'cpu'
    print('Using device: ', device)

    prepared_dataset_filename, data_np, veh_h_np, veh_pos_np, best_beam_pair_index_np \
        = get_prepared_dataset(preprocess_mode, DS_start, DS_end, M_t, M_r, freq, n_pilot, N_bs, P_t, P_noise)
    data_torch = np2torch(data_np,device) 
    veh_h_torch = np2torch(veh_h_np,device) 
    veh_pos_torch = np2torch(veh_pos_np,device) 
    best_beam_pair_index_torch = np2torch(best_beam_pair_index_np,device)
    
    result_save_dir, plt_save_dir, model_save_dir, log_save_dir = get_save_dirs(prepared_dataset_filename)
    
    num_epochs =  50
    pretrained_model_path = None
    # 运行训练
    model, train_loss_list, train_acc_list, train_mae_list, train_mse_list, \
    train_bestBS_mae_list, train_bestBS_mse_list, train_bestBS_acc_list, \
    val_loss_list, val_acc_list, val_mae_list, val_mse_list, \
    val_bestBS_mae_list, val_bestBS_mse_list, val_bestBS_acc_list = \
        train_gainlevelpred_model(num_epochs, device, data_torch, veh_h_torch, best_beam_pair_index_torch, M_t, M_r, pretrained_model_path, model_save_dir, pos_in_data=(preprocess_mode==2))
    train_result_name_list = split_string("model, train_loss_list, train_acc_list, train_mae_list, train_mse_list, \
    train_bestBS_mae_list, train_bestBS_mse_list, train_bestBS_acc_list, \
    val_loss_list, val_acc_list, val_mae_list, val_mse_list, \
    val_bestBS_mae_list, val_bestBS_mse_list, val_bestBS_acc_list")
    
    save_name = f"gainlevelpred_dimIn{model.feature_input_dim}Out{model.num_dBlevel}_valAcc{max(val_acc_list):.2f}%_BBSMAE{min(val_bestBS_mae_list):.2f}"
    save_name = save_name + time.strftime('_%Y-%m-%d_%H:%M:%S', time.gmtime(time.time() + 8 * 3600))
    torch.save(model.state_dict(), os.path.join(model_save_dir, save_name+'.pth'))
    log_dict = save_log(locals(), train_result_name_list, os.path.join(log_save_dir,save_name+'.pkl'))
    plot_gainlevelpred(os.path.join(plt_save_dir,save_name+'.png'), log_dict)