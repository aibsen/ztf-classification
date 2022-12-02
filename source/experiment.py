from torch import nn
import torch
import os
import sys
import numpy as np
import torch.optim as optim
from seq2seq_experiment1 import Seq2SeqExperiment
from classification_experiment import ClassificationExperiment
import pandas as pd


class Experiment(nn.Module):

    def __init__(self, network_model, 
        experiment_name,
        num_epochs=100,
        num_output_classes=4, 
        learning_rate=1e-03,
        batch_size = 64, 
        train_data=None, 
        val_data=None,
        test_data=None,
        weight_decay_coefficient=1e-03, 
        patience=3,
        validation_step=3,
        type = 'seq2seq',
        pick_up = False):

        super(Experiment, self).__init__()

        if torch.cuda.is_available():
            self.device = torch.device('cuda')
            os.environ["CUDA_VISIBLE_DEVICES"] = "0"
            # print("using GPU")

        self.experiment_name = experiment_name
        self.model = network_model
        self.model.to(self.device)
        self.model.reset_parameters()
        self.patience = patience
        self.validation_step = validation_step
        self.batch_size = batch_size
        self.num_epochs = num_epochs
        self.num_output_classes = num_output_classes

        self.train_data=None
        self.val_data=None
        self.test_data=None

        if self.validation_step > self.num_epochs:
            print("Validation step should be less than the number of epochs so at least one run is possible")
            sys.exit()
        
        if self.patience > int(self.num_epochs/self.validation_step):
            print("Infinite patience, early stopping won't be an option")
        
        if train_data:
            train_loader = torch.utils.data.DataLoader(train_data, batch_size=batch_size, shuffle=True)
            self.train_data = train_loader

        if val_data:
            val_loader = torch.utils.data.DataLoader(val_data, batch_size=batch_size, shuffle=True)
            self.val_data = val_loader

        if test_data:
            test_loader = torch.utils.data.DataLoader(test_data,batch_size=batch_size,shuffle=True)
            self.test_data = test_loader

        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate, amsgrad=False,
                                    weight_decay=weight_decay_coefficient)


        # Generate the directory names
        self.experiment_folder = os.path.abspath(experiment_name)
        self.experiment_logs = os.path.abspath(os.path.join(self.experiment_folder, "result_outputs"))
        self.experiment_saved_models = os.path.abspath(os.path.join(self.experiment_folder, "saved_models"))

        if not os.path.exists(self.experiment_folder):  # If experiment directory does not exist
            os.mkdir(self.experiment_folder)  # create the experiment directory
            os.mkdir(self.experiment_logs)  # create the experiment log directory
            os.mkdir(self.experiment_saved_models)  # create the experiment saved models directory

        # Set best model f1_score to be at 0 and the best epoch to be num_epochs, since we are just starting
        self.best_epoch = num_epochs
        self.state = {}

        if type == 'classification':
            self.instance = ClassificationExperiment(self)
            self.criterion = nn.CrossEntropyLoss().to(self.device)  # send the loss computation to the GPU
            self.best_f1 = 0
        else:
            self.instance = Seq2SeqExperiment(self)
            try:
                self.model.reset_loss(num_epochs)
                self.criterion = self.model.criterion
            except Exception as e:
                print("!! USING MSE INSTEAD OF CUSTOM")
                print(e)
                self.criterion = torch.nn.MSELoss(self.device)

            self.best_loss = np.inf
        self.pickup = pick_up

    def save_model(self, model_save_name):
        save_path = os.path.join(self.experiment_saved_models, model_save_name)
        torch.save(self.state,save_path)

    def load_model(self,model_save_name="final_model_pth.tar"):
        try:
            save_path = os.path.join(self.experiment_saved_models, model_save_name)
            print("loading model from {}".format(save_path))
            self.state = torch.load(f=save_path)
            # print(self.state['optimizer'])
            self.model.load_state_dict(state_dict=self.state['model'])
            self.optimizer.load_state_dict(state_dict=self.state['optimizer'])
            self.best_epoch = self.state['epoch']
        except Exception as e:
            print("could not find saved model in {}".format(save_path))
            print(e)

    def save_statistics(self, stats, fn, stats_keys):
        fn = fn if isinstance(self.instance, ClassificationExperiment) else "reconstruction_"+fn
        stats_df = pd.DataFrame(stats.cpu().numpy() , columns = stats_keys)
        stats_df = stats_df[stats_df.epoch>=0]
        stats_df.epoch = stats_df.epoch.astype(int)
        stats_df.to_csv(self.experiment_logs+'/'+fn ,sep=',',index=False)

    def run_train_phase(self,train_data_name='',
        model_load_name='best_validation_model.pth.tar',
        model_save_name='best_validation_model.pth.tar'):

        if self.pickup:
            self.load_model(model_save_name=model_load_name)
        self.instance.run_train_phase(load_model=False,
            model_save_name=model_save_name,
            train_data_name=train_data_name)

    def run_final_train_phase(self, data_loaders=None, n_epochs=None,\
        model_load_name='final_model.pth.tar',
        model_save_name='final_model.pth.tar', data_name='final_training',train_data_name=''):
        if self.pickup:
            self.load_model(model_save_name=model_load_name)
        self.instance.run_final_train_phase(data_loaders,n_epochs,model_save_name,
            data_name,train_data_name=train_data_name)

    def run_test_phase(self, data=None, model_name ='final_model.pth.tar',\
        data_name='test'):
        self.instance.run_test_phase(data, model_name, data_name)

    def run_test_phase(self, data=None, model_name ='final_model.pth.tar',\
        data_name='test'):
        self.instance.run_test_phase(data, model_name, data_name)

    def run_prediction(self, data=None, model_name='final_model.pth.tar',\
        data_name='predicted'):
        # try:
        self.instance.run_prediction(data=data,model_name=model_name,data_name=data_name)
        # except Exception as e:
            # print("only seq2seq experiments predict sequences")
            # print(e)
            # sys.exit(1)


    def run_experiment(self):
        if self.train_data and self.val_data:
            print("")
            print("Starting training phase")
            print("")
            self.instance.run_train_phase()
        #     print("")
        #     print("Starting final training phase")
        #     print("")
        #     self.instance.run_final_train_phase()

        if self.test_data:
        #     print("")
        #     print("Starting test phase")
        #     print("")
            self.instance.run_test_phase(self.test_data)
    