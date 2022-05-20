from torch import nn
from copy import deepcopy
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
import tqdm
import os
import numpy as np
import time
from sklearn.model_selection import StratifiedKFold
from datasets import LCs, CachedLCs
from data_samplers import CachedRandomSampler
from dataset_utils import cached_crossvalidator_split
from experiment import Experiment
from utils import find_best_epoch
import pandas as pd

class CVExperiment(nn.Module):
    def __init__(self, exp_name,exp_params=None,train_data=None,test_data=None,k=5,seed=None):

        super(CVExperiment, self).__init__()
        self.experiment_folder = os.path.abspath(exp_name)
        self.experiment_logs = os.path.abspath(os.path.join(self.experiment_folder, "result_outputs"))
        self.experiment_folds = os.path.abspath(os.path.join(self.experiment_folder, "folds"))
        self.experiment_saved_models = os.path.abspath(os.path.join(self.experiment_folder, "saved_models"))

        if not os.path.exists(self.experiment_folder):  # If experiment directory does not exist
            os.mkdir(self.experiment_folder)  # create the experiment directory
            os.mkdir(self.experiment_logs)  # create the experiment log directory
            os.mkdir(self.experiment_folds)  # create the experiment fold directories
            os.mkdir(self.experiment_saved_models)  # create the experiment fold directories

        self.exp_params = exp_params
        self.k = k
        self.train_data = train_data
        self.test_data = test_data
        self.best_val_fold = None
        self.best_fold = None
        self.batch_size = self.exp_params['batch_size']
        
        if train_data:
            self.train_length = len(train_data)
            idxs = np.arange(self.train_length)
            targets = train_data.targets
            kf = StratifiedKFold(n_splits=k)
            self.kfs = kf.split(idxs,targets)

    def save_fold_statistics(self, summary_file, metric='f1'):
        stats = {'epoch':[],'accuracy':[],'loss':[],'f1':[],'precision':[],'recall':[]}
        for k in np.arange(self.k):
            exp_name = self.experiment_folds+"/fold_k"+str(k+1)+"/result_outputs"
            summary = pd.read_csv(exp_name+"/"+summary_file)
            stats_at_break = summary[summary[metric] == summary[metric].max()]
            for k in stats.keys():
                stats[k].append(stats_at_break.iloc[0][k])

        best_fold = stats[metric].index(max(stats[metric]))+1    
        stats = {k: sum(v)/len(v) for k, v in stats.items()}
        stats_df =  pd.DataFrame(stats, index=[0]).rename(columns = lambda c : 'mean_'+ c)
        stats_df.mean_epoch = stats_df.mean_epoch.apply(np.ceil).astype(int)
        if summary_file == 'validation_summary.csv':
            self.best_fold = best_fold    
            self.mean_best_epoch = int(stats_df.iloc[0]['mean_epoch'])
        stats_df.to_csv(self.experiment_logs+"/"+summary_file,index=False)

    def run_experiment(self, test_data_name="test"):
        if self.train_data:
            self.run_train_phase()
        if self.train_data and self.test_data:
            self.run_final_train_phase()
            self.run_test_phase(test_data_name)
        elif self.test_data:
            self.run_test_phase(test_data_name)

    def run_train_phase(self):
        for k,(tr,val) in enumerate(self.kfs):
            train_dataset = torch.utils.data.Subset(self.train_data, tr)
            val_dataset = torch.utils.data.Subset(self.train_data, val)

            experiment = Experiment(
                network_model = self.exp_params["network_model"],
                experiment_name = self.experiment_folds+"/fold_k"+str(k+1),
                num_epochs = self.exp_params["num_epochs"],
                learning_rate = self.exp_params["learning_rate"],
                weight_decay_coefficient = self.exp_params["weight_decay_coefficient"],
                batch_size = self.exp_params["batch_size"],
                train_data = train_dataset,
                val_data = val_dataset,
                test_data = self.test_data,
                num_output_classes=self.exp_params["num_output_classes"],
                patience = self.exp_params["patience"],
                validation_step = self.exp_params["validation_step"]
            )

            # start_time = time.time()
            experiment.run_train_phase()
            # print("--- %s seconds ---" % (time.time() - start_time))


        self.save_fold_statistics("validation_summary.csv")
        self.save_fold_statistics("training_summary.csv") #there's an error here that I don't have time to fix: I'm saving best training stats, but kept last training epoch results.



        #final run of cv experiment??
    def run_final_train_phase(self):

        experiment = Experiment(
            network_model = self.exp_params["network_model"],
            experiment_name = self.experiment_folder,
            num_epochs = self.exp_params["num_epochs"],
            learning_rate = self.exp_params["learning_rate"],
            weight_decay_coefficient = self.exp_params["weight_decay_coefficient"],
            batch_size = self.exp_params["batch_size"],
            num_output_classes=self.exp_params["num_output_classes"],
        )

        train_loader = torch.utils.data.DataLoader(self.train_data, batch_size=self.batch_size, shuffle=True)
        start_time = time.time()
        # print(self.mean_best_epoch)

        experiment.run_final_train_phase(data_loaders=[train_loader], n_epochs=self.mean_best_epoch)
        # print("--- %s seconds ---" % (time.time() - start_time))

    def run_test_phase(self, test_data_name='test'):

        exp_name = self.experiment_folder
        experiment = Experiment(
            network_model = self.exp_params["network_model"],
            experiment_name = exp_name,
            batch_size = self.exp_params["batch_size"],
            num_output_classes= self.exp_params["num_output_classes"],
        )

        test_loader = torch.utils.data.DataLoader(self.test_data, batch_size=self.batch_size, shuffle=True)
        # start_time = time.time()
        experiment.run_test_phase(data=test_loader,model_idx=self.mean_best_epoch,data_name=test_data_name)
        # print("--- %s seconds ---" % (time.time() - start_time))


    # def get_folds_from_folders(self):
    #     rootdir = self.experiment_folds
    #     folds = os.walk(rootdir).__next__()[1]
    #     return folds


    # def get_best_fold(self,summary_filename="test_summary.csv",metric="f1"):
    #     folds = self.get_folds_from_folders()
    #     best_k = -1
    #     best_metric = -1
    #     for fold in folds:
    #         summary = self.experiment_folds+"/"+fold+"/result_outputs/"+summary_filename
    #         summary_df=pd.read_csv(summary)
    #         new_metric = summary_df[metric].values
    #         # print(summary_df)
    #         # print(new_metric)
    #         if new_metric>best_metric: #this would only work for acc and f1
    #             best_metric = new_metric
    #             best_k = fold[-1] #only works for 9 or less folds
        
    #     return best_k, best_metric

    