import argparse
from dataread import data_train_raw, data_test_raw, ShipTrajData
import torch
import numpy as np
from transformer.Models import Transformer, MLP
import os
from torch import optim
from torch.nn import functional as F
import random
from matplotlib import pyplot as plt
from tensorboardX import SummaryWriter
import time
from torch.utils.data import Dataset, DataLoader
import tqdm
log_writer = SummaryWriter()

os.environ['CUDA_LAUNCH_BLOCKING'] ='1'

def DrawTrajectory(tra_pred,tra_true):
    tra_pred[:,:,0]=tra_pred[:,:,0]*0.00063212+110.12347
    tra_true[:,:,0]=tra_true[:,:,0]*0.00063212+110.12347
    tra_pred[:,:,1]=tra_pred[:,:,1]*0.000989464+20.023834
    tra_true[:,:,1]=tra_true[:,:,1]*0.000989464+20.023834
    idx=random.randrange(0,tra_true.shape[0])
    plt.figure(figsize=(9,6),dpi=150)
    pred=tra_pred[idx,:,:].cpu().detach().numpy()
    true=tra_true[idx,:,:].cpu().detach().numpy()
    np.savetxt('pred_true.txt',np.vstack((pred,true)))
    print("A track includes a total of {0} detection points,and their longtitude and latitude differences are".format(pred.shape[0]))
    for i in range(pred.shape[0]):
        print("{0}:({1} degrees,{2} degrees)".format(i+1,abs(pred[i,0]-true[i,0]),abs(pred[i,1]-true[i,1])))
    print('\n')
    plt.plot(pred[:,0],pred[:,1], "r-o")
    plt.plot(true[:,0],true[:,1], "b-*")
    plt.show()

def cal_performance(tra_pred,tra_true):
    return F.mse_loss(tra_pred,tra_true)
def adjust_learning_rate(optimizer, epoch):
    opt.lr =max(opt.lr-1.3e-7, 1e-4)
    optimizer.param_groups[0]['lr']=opt.lr

def train(model, dataloader, optimizer, device, opt):
    for epoch_i in range(opt.start_epoch,opt.epoch):
        start_time = time.time()
        model.train()
        total_loss = 0 # loss in each epoch
        for idx, data in enumerate(dataloader):
            optimizer.zero_grad()
            tra_pred = model(input_data=data.to(device).to(torch.float32), device=device)

            # backward and update parameters
            loss = cal_performance(tra_pred, data[:, 1:, :].to(device).to(torch.float32))
            loss.backward()
            optimizer.step()
            adjust_learning_rate(optimizer, epoch_i)
            total_loss += loss.item()
        log_writer.add_scalar("loss", total_loss, epoch_i)
        log_writer.add_scalar("lr", optimizer.param_groups[0]['lr'], epoch_i)
        if epoch_i % 1000 == 0 or epoch_i==opt.epoch-1:
            end_time = time.time()
            print("training: %d/%d, total_loss = %lf, iter_cost=%.3fs, time_cost: %.2fs/%.2fs,learning_rate:%f" \
                % (epoch_i,opt.epoch,total_loss,end_time - start_time,(end_time - start_time)*epoch_i,\
                    (end_time - start_time)*(opt.epoch-epoch_i),optimizer.param_groups[0]['lr']))
        # another method to save model
            checkpoint = {
                "net":model.state_dict(),
                "optimizer":optimizer.state_dict(),
                "epoch":epoch_i}

            if not os.path.isdir("./checkpoint"):
                os.mkdir("./checkpoint")
            torch.save(checkpoint, "./checkpoint/ckpt.pth")
            if epoch_i==opt.epoch-1:
                DrawTrajectory(tra_pred, data[:, 1:, :])

    torch.save(model,'model.pt')
    # another method to save model

    print("Train Finish")

def test(model, dataloader, device):
    total_loss = 0
    for idx, data in enumerate(dataloader):
        tra_pred = model(input_data=data.to(device).to(torch.float32),device=device)
        loss = cal_performance(tra_pred, data[:, 1:, :].to(device).to(torch.float32))
    total_loss += loss.item()
    # DrawTrajectory(tra_pred, data[:, 1:, :])
    print("Test Finish, total_loss = {}".format(total_loss))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-epoch', type=int, default=30000)
    parser.add_argument('-b', '--batch_size', type=int, default=140)
    parser.add_argument('-d_model', type=int, default=512)
    parser.add_argument('-d_inner_hid', type=int, default=2048)
    parser.add_argument('-d_k', type=int, default=64)
    parser.add_argument('-d_v', type=int, default=64)
    parser.add_argument('-lr', type=float, default=0.001)
    parser.add_argument('-n_head', type=int, default=2)
    parser.add_argument('-n_layers', type=int, default=1)
    parser.add_argument('-dropout', type=float, default=0.1)
    parser.add_argument('-do_train', type=bool, default=True)
    parser.add_argument('-start_epoch', type=int, default=0)
    parser.add_argument('-do_retrain', type=bool, default=True)
    parser.add_argument('-do_eval', type=bool, default=True)
    parser.add_argument('-use_mlp', type=bool, default=False)

    opt = parser.parse_args()
    opt.d_word_vec = opt.d_model
    device="cuda:0"
    #device="cpu"

    transformer = Transformer(
        500,
        500,
        d_k=opt.d_k,
        d_v=opt.d_v,
        d_model=opt.d_model,
        d_word_vec=opt.d_word_vec,
        d_inner=opt.d_inner_hid,
        n_layers=opt.n_layers,
        n_head=opt.n_head,
        dropout=opt.dropout,
    ).to(device)

    if opt.do_train == True:
        # data=torch.from_numpy(np.array(data_train)).to(device).to(torch.float32)
        data_train = ShipTrajData(data_train_raw)
        train_loader = DataLoader(dataset=data_train, batch_size=opt.batch_size, shuffle=False)

        mlp = MLP(10,25,50,10).to(device)

        parameters = mlp.parameters() if opt.use_mlp else transformer.parameters()
        optimizer =optim.Adam(parameters, lr=opt.lr)

        model_train = transformer
        if opt.use_mlp:
            model_train = mlp

        if not opt.do_retrain:
            checkpoint = torch.load("./checkpoint/ckpt.pth")
            transformer.load_state_dict(checkpoint['net'])
            optimizer.load_state_dict(checkpoint['optimizer'])
            opt.start_epoch=checkpoint['epoch']

        train(
            model=model_train,
            dataloader=train_loader,
            optimizer=optimizer,
            device=device,
            opt=opt
        )



    if opt.do_eval == True:
        # data=torch.from_numpy(np.array(data_train)).to(device).to(torch.float32)
        data_test = ShipTrajData(data_train_raw)
        test_loader = DataLoader(dataset=data_test, batch_size=opt.batch_size, shuffle=False)
        model=torch.load('model.pt').to(device)
        #ckpt=torch.load('checkpoint/ckpt1_shuffle_8000epochs.pth')
        #transformer.load_state_dict(ckpt['net'])

        test(
            model=model,
            dataloader=test_loader,
            device=device
        )







