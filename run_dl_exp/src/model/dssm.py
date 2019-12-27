import torch
import torch.nn.functional as F

class DSSM(torch.nn.Module):
    def __init__(self, inputSize):
        super().__init__()
        self.embed = torch.nn.Embedding(inputSize, 128, padding_idx=0)  # trans one-hot vector to 300 dimensions
        ## Tower 1 for context feature
        self.t1_bias1 = torch.nn.Parameter(torch.zeros((128,)))
        self.t1_fc2 = torch.nn.Linear(128, 32, bias=True)  # add 1 for padding_idx
        #self.t1_fc3 = torch.nn.Linear(100, 32, bias=True)  # add 1 for padding_idx
        ## Tower 2 for item feature
        self.t2_bias1 = torch.nn.Parameter(torch.zeros((128,)))
        self.t2_fc2 = torch.nn.Linear(128, 32, bias=True)  # add 1 for padding_idx
        #self.t2_fc3 = torch.nn.Linear(100, 32, bias=True)  # add 1 for padding_idx

    def forward(self, x1, x2, use_relu=False):
        if use_relu:
            act = torch.relu
        else:
            act = torch.tanh
        ## Tower 1
        x1 = torch.sum(self.embed(x1), dim = 1) + self.t1_bias1
        x1 = act(x1)
        x1 = self.t1_fc2(x1) 
        x1 = act(x1)
        #x1 = self.t1_fc3(x1) 
        #x1 = act(x1)
        ## Tower 2 
        x2 = torch.sum(self.embed(x2), dim = 1) + self.t2_bias1
        x2 = act(x2)
        x2 = self.t2_fc2(x2) 
        x2 = act(x2)
        #x2 = self.t2_fc3(x2) 
        #x2 = act(x2)
        ## merge
        out = torch.sigmoid(torch.sum(x1*x2, dim = 1))
        #print(out.size())
        #return out.squeeze(1)
        return out