import numpy as np
import torch
import torch.nn.functional as F


class FeaturesLinear(torch.nn.Module):

    def __init__(self, field_dims, output_dim=1):
        super().__init__()
        self.fc = torch.nn.Embedding(sum(field_dims), output_dim, padding_idx=0)
        self.bias = torch.nn.Parameter(torch.zeros((output_dim,)))
        self.offsets = torch.Tensor(np.array((0, *np.cumsum(field_dims)[:-1]), dtype=np.long))
        torch.nn.init.xavier_uniform_(self.fc.weight.data[1:, :])

    #def forward(self, x):
    def forward(self, x_field, x, x_val=None):  #[batch_size, 3, num_feats] [[[0,1,2,3,4,5,6],[0,1,2,3]]] (1, num_fields, num_dims) 
        """
        :param x: Long tensor of size ``(batch_size, num_fields)``
        """
        #x = x + x.new_tensor(self.offsets).unsqueeze(0)
        x = x + torch.as_tensor(self.offsets[x_field.flatten()], dtype=torch.long, device=x.device).reshape(x.shape)
        if x_val is None:
            return torch.sum(self.fc(x), dim=1) + self.bias
        else:
            return torch.sum(torch.mul(self.fc(x), x_val.unsqueeze(2)), dim=1) + self.bias

class FeaturesEmbedding(torch.nn.Module):

    def __init__(self, field_dims, embed_dim):
        super().__init__()
        self.num_fields = len(field_dims)
        #self.embeddings = torch.nn.ModuleList([torch.nn.Embedding(field_dims[i] + 1, embed_dim, padding_idx=0) for i in range(1, self.num_fields)])
        #for embedding in self.embeddings:
        #    torch.nn.init.xavier_uniform_(embedding.weight.data[1:, :])
        self.embedding = torch.nn.Embedding(sum(field_dims), embed_dim, padding_idx=0)
        self.offsets = torch.Tensor(np.array((0, *np.cumsum(field_dims)[:-1]), dtype=np.long))
        torch.nn.init.xavier_uniform_(self.embedding.weight.data[1:, :])

    def forward(self, x_field, x, x_val=None):  #[batch_size, 3, num_feats] [[[0,1,2,3,4,5,6],[0,1,2,3]]] (1, num_fields, num_dims) 
        """
        :param x: Long tensor of size ``(batch_size, num_feats)``
        """
        x = x + torch.as_tensor(self.offsets[x_field.flatten()], dtype=torch.long, device=x.device).reshape(x.shape)
        if x_val is None:
            xs = [self.embedding((x)*(x_field==f).to(torch.long)).sum(dim=1) 
                    for f in range(1, self.num_fields)]
        else:
            xs = [torch.mul(self.embedding((x)*(x_field==f).to(torch.long)), 
                (x_val*(x_field==f).to(torch.float)).unsqueeze(2)).sum(dim=1) 
                for f in range(1, self.num_fields)]
        embedded_x = torch.stack(xs, dim=1)

        #x = x + x.new_tensor(self.offsets[x_field.flatten()]).reshape(x.shape)
        #embedded_x = self.embedding(x)
        #if x_val is not None:
        #    embedded_x = torch.mul(embedded_x, x_val.unsqueeze(2))  # field 1 embedding for cxt: (batch_size, cxt_nonzero_feature_num, embed_dim)
        #trans = torch.zeros(x.shape[0], self.num_fields, x.shape[1]).to(x.device)
        #trans[torch.arange(x.shape[0]).unsqueeze(0).transpose(0,1).expand(-1, x.shape[1]).flatten(), 
        #      x_field.flatten(), 
        #      torch.arange(x.shape[1]).unsqueeze(0).expand(x.shape[0], -1).flatten()] = 1
        #embedded_x = torch.bmm(trans, embedded_x)
        
        return embedded_x 


class FieldAwareFactorizationMachine(torch.nn.Module):

    def __init__(self, field_dims, embed_dim):
        super().__init__()
        self.num_fields = len(field_dims)
        self.embeddings = torch.nn.ModuleList([
            FeaturesEmbedding(field_dims, embed_dim) for _ in range(self.num_fields - 1)
        ])
        #self.offsets = np.array((0, *np.cumsum(field_dims)[:-1]), dtype=np.long) 

    def forward(self, x_field, x, x_val=None):
        """
        :param x: Long tensor of size ``(batch_size, num_fields)``
        """
        #x = x + x.new_tensor(self.offsets).unsqueeze(0)
        #xs = [self.embeddings[i](x) for i in range(self.num_fields)]
        #x = x + x.new_tensor(self.offsets[x_field.flatten()]).reshape(x.shape)
        xs = [self.embeddings[f](x_field, x, x_val) for f in range(self.num_fields - 1)]  # field_num, bs, field_num, embed_dim
        ix = list()
        for i in range(self.num_fields - 2):
            for j in range(i + 1, self.num_fields - 1):
                ix.append(xs[j][:, i] * xs[i][:, j])
        ix = torch.stack(ix, dim=1)
        return ix


class FactorizationMachine(torch.nn.Module):

    def __init__(self, reduce_sum=True):
        super().__init__()
        self.reduce_sum = reduce_sum

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        square_of_sum = torch.sum(x, dim=1) ** 2
        sum_of_square = torch.sum(x ** 2, dim=1)
        ix = square_of_sum - sum_of_square
        if self.reduce_sum:
            ix = torch.sum(ix, dim=1, keepdim=True)
        return 0.5 * ix


class MultiLayerPerceptron(torch.nn.Module):

    def __init__(self, input_dim, embed_dims, dropout, output_layer=True):
        super().__init__()
        layers = list()
        for embed_dim in embed_dims:
            layers.append(torch.nn.Linear(input_dim, embed_dim))
            #layers.append(torch.nn.BatchNorm1d(embed_dim))
            layers.append(torch.nn.ReLU())
            layers.append(torch.nn.Dropout(p=dropout))
            input_dim = embed_dim
        if output_layer:
            layers.append(torch.nn.Linear(input_dim, 1))
        self.mlp = torch.nn.Sequential(*layers)

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        return self.mlp(x)


class InnerProductNetwork(torch.nn.Module):

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        num_fields = x.shape[1]
        row, col = list(), list()
        for i in range(num_fields - 1):
            for j in range(i + 1, num_fields):
                row.append(i), col.append(j)
        return torch.sum(x[:, row] * x[:, col], dim=2)


class OuterProductNetwork(torch.nn.Module):

    def __init__(self, num_fields, embed_dim, kernel_type='mat'):
        super().__init__()
        num_ix = num_fields * (num_fields - 1) // 2
        if kernel_type == 'mat':
            kernel_shape = embed_dim, num_ix, embed_dim
        elif kernel_type == 'vec':
            kernel_shape = num_ix, embed_dim
        elif kernel_type == 'num':
            kernel_shape = num_ix, 1
        else:
            raise ValueError('unknown kernel type: ' + kernel_type)
        self.kernel_type = kernel_type
        self.kernel = torch.nn.Parameter(torch.zeros(kernel_shape))
        torch.nn.init.xavier_uniform_(self.kernel.data)

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        num_fields = x.shape[1]
        row, col = list(), list()
        for i in range(num_fields - 1):
            for j in range(i + 1, num_fields):
                row.append(i), col.append(j)
        p, q = x[:, row], x[:, col]
        if self.kernel_type == 'mat':
            kp = torch.sum(p.unsqueeze(1) * self.kernel, dim=-1).permute(0, 2, 1)
            return torch.sum(kp * q, -1)
        else:
            return torch.sum(p * q * self.kernel.unsqueeze(0), -1)


class CrossNetwork(torch.nn.Module):

    def __init__(self, input_dim, num_layers):
        super().__init__()
        self.num_layers = num_layers
        self.w = torch.nn.ModuleList([
            torch.nn.Linear(input_dim, 1, bias=False) for _ in range(num_layers)
        ])
        self.b = torch.nn.ParameterList([
            torch.nn.Parameter(torch.zeros((input_dim,))) for _ in range(num_layers)
        ])

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        x0 = x
        for i in range(self.num_layers):
            xw = self.w[i](x)
            x = x0 * xw + self.b[i] + x
        return x


class AttentionalFactorizationMachine(torch.nn.Module):

    def __init__(self, embed_dim, attn_size, dropouts):
        super().__init__()
        self.attention = torch.nn.Linear(embed_dim, attn_size)
        self.projection = torch.nn.Linear(attn_size, 1)
        self.fc = torch.nn.Linear(embed_dim, 1)
        self.dropouts = dropouts

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        num_fields = x.shape[1]
        row, col = list(), list()
        for i in range(num_fields - 1):
            for j in range(i + 1, num_fields):
                row.append(i), col.append(j)
        p, q = x[:, row], x[:, col]
        inner_product = p * q
        attn_scores = F.relu(self.attention(inner_product))
        attn_scores = F.softmax(self.projection(attn_scores), dim=1)
        attn_scores = F.dropout(attn_scores, p=self.dropouts[0])
        attn_output = torch.sum(attn_scores * inner_product, dim=1)
        attn_output = F.dropout(attn_output, p=self.dropouts[1])
        return self.fc(attn_output)


class CompressedInteractionNetwork(torch.nn.Module):

    def __init__(self, input_dim, cross_layer_sizes, split_half=True):
        super().__init__()
        self.num_layers = len(cross_layer_sizes)
        self.split_half = split_half
        self.conv_layers = torch.nn.ModuleList()
        prev_dim, fc_input_dim = input_dim, 0
        for cross_layer_size in cross_layer_sizes:
            self.conv_layers.append(torch.nn.Conv1d(input_dim * prev_dim, cross_layer_size, 1,
                                                    stride=1, dilation=1, bias=True))
            if self.split_half:
                cross_layer_size //= 2
            prev_dim = cross_layer_size
            fc_input_dim += prev_dim
        self.fc = torch.nn.Linear(fc_input_dim, 1)

    def forward(self, x):
        """
        :param x: Float tensor of size ``(batch_size, num_fields, embed_dim)``
        """
        xs = list()
        x0, h = x.unsqueeze(2), x
        for i in range(self.num_layers):
            x = x0 * h.unsqueeze(1)
            batch_size, f0_dim, fin_dim, embed_dim = x.shape
            x = x.view(batch_size, f0_dim * fin_dim, embed_dim)
            x = F.relu(self.conv_layers[i](x))
            if self.split_half and i != self.num_layers - 1:
                x, h = torch.split(x, x.shape[1] // 2, dim=1)
            else:
                h = x
            xs.append(x)
        return self.fc(torch.sum(torch.cat(xs, dim=1), 2))


if __name__ == '__main__':
    torch.manual_seed(0)
    field_dims = [1, 4, 5]
    fl = FeaturesLinear(field_dims, 1) 
    fe = FeaturesEmbedding(field_dims, 2)
    fm = FactorizationMachine(True)
    ffm = FieldAwareFactorizationMachine(field_dims, 2)
    print(fl.fc.weight.data)
    print(fl.bias.data)
    print(fe.embedding.weight.data)
    x_field = torch.Tensor([[1,1,2,2,0,0], [1,2,1,0,0,0]]).to(torch.long)
    x = torch.tensor([[0,3,1,4,0,0], [2,2,2,0,0,0]])
    x_val = torch.Tensor([[1,1,1,0,0,0], [0.5,1,0.5,0,0,0]])
    print(x_field, x, x_val)
    print(fl.forward(x, x_val))
    print(fe.forward(x_field, x, x_val))
    print(fm(fe.forward(x_field, x, x_val)))
    print(ffm(x_field, x, x_val))

