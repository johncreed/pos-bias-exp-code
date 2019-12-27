import os
import time
import sys
import torch
import numpy as np
import lmdb
import shutil
import struct
from tqdm import tqdm
from pathlib import Path
from torch.utils.data import Dataset, DataLoader

class PositionDataset(Dataset):
    def __init__(self, dataset_path=None, data_prefix='tr', rebuild_cache=False, tr_max_dim=-1, test_flag=False):
        self.tr_max_dim = tr_max_dim
        self.test_flag = test_flag
        data_path = os.path.join(dataset_path, data_prefix + '.svm')
        item_path = os.path.join(dataset_path, 'item.svm')
        assert Path(data_path).exists(), "%s does not exist!"%data_path
        cache_path = os.path.join(dataset_path, data_prefix + '.lmdb')

        if rebuild_cache or not Path(cache_path).exists():
            shutil.rmtree(cache_path, ignore_errors=True)
            if dataset_path is None:
                raise ValueError('create cache: failed: dataset_path is None')
            self.__build_cache(data_path, item_path, cache_path)
        print('Reading data from %s.'%(cache_path))
        self.env = lmdb.open(cache_path, create=False, lock=False, readonly=True)
        with self.env.begin(write=False) as txn:
            self.max_dim = np.frombuffer(txn.get(b'max_dim'), dtype=np.int32)[0] + 1  # idx from 0 to max_dim_in_svmfile, 0 for padding
            self.item_num = np.frombuffer(txn.get(b'item_num'), dtype=np.int32)[0]
            self.length = 10*(txn.stat()['entries'] - self.item_num - 2) if not self.test_flag else self.item_num*(txn.stat()['entries'] - self.item_num - 2)
    
    def __build_cache(self, data_path, item_path, cache_path):
        max_dim = np.zeros(1, dtype=np.int32)
        item_num = np.zeros(1, dtype=np.int32)
        with lmdb.open(cache_path, map_size=int(1e11)) as env:
            i = 0
            with open(item_path, 'r') as fi:
                pbar = tqdm(fi, mininterval=1, smoothing=0.1)
                pbar.set_description('Create position dataset cache: setup lmdb for item')
                for line in pbar:
                    line = line.strip()
                    item = np.array(sorted([int(j.split(':')[0]) for j in line.split(' ')]), dtype=np.int32)
                    with env.begin(write=True) as txn:
                        txn.put(b'item_%d'%i, item.tobytes())
                        i += 1
            item_num[0] = i
                
            for buf in self.__yield_buffer(data_path):
                with env.begin(write=True) as txn:
                    for key, value, max_dim_buf in buf:
                        txn.put(key, value)
                        if  max_dim_buf > max_dim[0]:
                            max_dim[0] = max_dim_buf

            with env.begin(write=True) as txn:
                txn.put(b'max_dim', max_dim.tobytes())
                txn.put(b'item_num', item_num.tobytes())

    def __yield_buffer(self, data_path, buffer_size=int(1e5)):
        sample_idx, max_dim = 0, 0
        buf = list()
        with open(data_path, 'r') as fd:
            pbar = tqdm(fd, mininterval=1, smoothing=0.1)
            pbar.set_description('Create position dataset cache: setup lmdb for context')
            for line in pbar:
                line = line.strip()
                labels, context = line.split(' ', 1)
                labels = labels.split(',')
                context = [int(i.split(':')[0]) for i in context.split(' ')]
                pairs = list()
                for l in labels:   
                    try:
                        item_idx, flag = l.split(':')[:2]
                    except:
                        item_idx = l
                        flag = '1'
                    pairs.extend([int(item_idx), int(flag)])
                feature = pairs + sorted(context)
                if  feature[-1] > max_dim:
                    max_dim = feature[-1]
                feature = np.array(feature, dtype=np.int32)  # [label, item_idx, position, feature_idx]
                buf.append((struct.pack('>I', sample_idx), feature.tobytes(), max_dim))
                sample_idx += 1
                if sample_idx % buffer_size == 0:
                    yield buf
                    buf.clear()
            yield buf

    def __len__(self):
        return self.length

    def __getitem__(self, idx):  # idx = 10*context_idx + pos
        if not self.test_flag:
            context_idx = int(idx)//10
            pos = int(idx)%10
            with self.env.begin(write=False) as txn:
                np_array = np.frombuffer(txn.get(struct.pack('>I', context_idx)), dtype=np.int32)
                item_idx = np_array[pos*2]
                flag = np_array[pos*2 + 1]
                item = np.frombuffer(txn.get(b'item_%d'%item_idx), dtype=np.int32)
                data = np_array[20:]  # context
            pos += 1
        else:
            context_idx = int(idx)//self.item_num
            pos = 0
            with self.env.begin(write=False) as txn:
                np_array = np.frombuffer(txn.get(struct.pack('>I', context_idx)), dtype=np.int32)
                item_idx = int(idx)%self.item_num 
                flag = -1
                item = np.frombuffer(txn.get(b'item_%d'%item_idx), dtype=np.int32)
                data = np_array[2:]  # item + context
        if self.tr_max_dim > 0:
            data = data[data <= self.tr_max_dim]
        return {'context':data, 'item':item, 'label':flag, 'pos':pos, 'item_idx':item_idx}  # pos \in {1,2,...9,10}, 0 for no-position


    def get_max_dim(self):
        return self.max_dim

    def get_item_num(self):
        return self.item_num

if __name__ == '__main__':
    from torch.utils.data import DataLoader
    dataset = PositionDataset(dataset_path='../../../data/random', data_prefix='gt', rebuild_cache=False, tr_max_dim=-1, test_flag=1)
    print('Start loading!')
    #f = open('pos.svm', 'w')
    print(len(dataset))
    print(dataset.get_max_dim())
    for idx in range(len(dataset)):
        i = dataset[idx]
        data = np.hstack((i['item'], i['context'])) 
        label = i['label']
        pos = i['pos']
        #if 1 in sample_batched['label']:
        #    print(i_batch, sample_batched)
        #    break
        print(idx, data, label, pos)
        if idx > 1:
            break
        #data = ['%d:1'%i for i in sorted(sample_batched['data'])] 
        #label = "+1" if sample_batched['label'] else "-1"
        #f.write("%s %s\n"%(label, " ".join(data)))
    #f.close()