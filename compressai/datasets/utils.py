# Copyright 2020 InterDigital Communications, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path
import random,cv2
# from PIL import Image
import glob,os
from torch.utils.data import Dataset
import kornia
import numpy as np
import os,glob
import torch
from torchvision import transforms

MEAN = torch.tensor([0.485, 0.456, 0.406]).mean().unsqueeze(0)
STD = torch.tensor([0.229, 0.224, 0.225]).mean().unsqueeze(0)

#获取4个下采样对应的h
def get_H(im1,im2): #cv2.imread+RGB
    # im1 = cv2.imread('/home/ywz/database/aftercut/train/left/2009.png')
    # im2 = cv2.imread('/home/ywz/database/aftercut/train/right/2009.png')
    # im1 = cv2.cvtColor(im1, cv2.COLOR_BGR2RGB)  # (H,W,3)
    # im2 = cv2.cvtColor(im2, cv2.COLOR_BGR2RGB)
    H_list = []
    for resize_scale in [1]: #[1,2,4,8]: #[2, 4, 8, 16]:
        # print(im1.shape)
        # resize
        resize_im1 = cv2.resize(im1, (im1.shape[1] // resize_scale, im1.shape[0] // resize_scale))  # W,H
        resize_im2 = cv2.resize(im2, (im2.shape[1] // resize_scale, im2.shape[0] // resize_scale))
        #
        surf = cv2.xfeatures2d.SURF_create()
        kp1, des1 = surf.detectAndCompute(resize_im1, None)
        kp2, des2 = surf.detectAndCompute(resize_im2, None)
        # 匹配特征点描述子
        bf = cv2.BFMatcher()
        matches = bf.knnMatch(des1, des2, k=2)
        # 提取匹配较好的特征点
        good = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:
                good.append(m)
        # 通过特征点坐标计算单应性矩阵H
        # （findHomography中使用了RANSAC算法剔初错误匹配）
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        # 获取H后，但要放进tensor中的变换
        try:
            h = torch.from_numpy(H.astype(np.float32))  # 否则float64，与网络中的tensor不匹配！
        except:
            h = None
        #     print(resize_scale)
        # h_inv = torch.inverse(h) #求逆
        H_list.append(h)
    return H_list

class ImageFolder(Dataset):
    """Load an image folder database. Training and testing image samples
    are respectively stored in separate directories: ::
        - rootdir/
            - train/
                -left/
                    - 0.png
                    - 1.png
                -right/
            - test/
                -left/
                    - 0.png
                    - 1.png
                -right/
    Args:
        root (string): root directory of the dataset
        transform (callable, optional): a function or transform that takes in a
            PIL image and returns a transformed version
        split (string): split mode ('train' or 'val')
    """
    def __init__(self, root, transform=None,patch_size=(256,256), split='train',need_file_name = False,root2="",need_root2=False,root_add="",need_H=True): #扩展root2 用来单独训练质量增强的原质量对比数据集 #root_add 扩展数据集
        splitdir = Path(root) / split  # 相当于osp.join

        if not splitdir.is_dir():
            raise RuntimeError(f'Invalid directory "{root}"')

        splitdir_left = splitdir / "left"
        splitdir_right = splitdir / "right"

        self.left_list = sorted(glob.glob(os.path.join(splitdir_left,"*")))
        self.right_list = sorted(glob.glob(os.path.join(splitdir_right, "*")))
        #root2
        self.need_root2 = need_root2
        if self.need_root2:
            splitdir2 = Path(root2) / split  # 相当于osp.join

            if not splitdir2.is_dir():
                raise RuntimeError(f'Invalid directory "{root2}"')

            splitdir_left2 = splitdir2 / "left"
            splitdir_right2 = splitdir2 / "right"

            self.left_list2 = sorted(glob.glob(os.path.join(splitdir_left2, "*")))
            self.right_list2 = sorted(glob.glob(os.path.join(splitdir_right2, "*")))
        # end root2

        self.patch_size = patch_size
        #只保留了ToTensor
        self.transform = transform

        ###for homography 单独裁剪 不传参直接设定
        self.homopic_size = 256
        self.homopatch_size = 128
        self.rho = 45
        self.homotransforms = transforms.Compose(
            [
                # ywz
                # transforms.Resize(self.homopic_size),
                # #
                # transforms.CenterCrop(self.homopic_size),
                transforms.ToTensor(),
                transforms.Normalize(mean=MEAN, std=STD),
            ]
        )
        ########################################

        self.need_file_name = need_file_name
        self.need_H = need_H
        #添加数据集
        # def add_datasets(self,,split="train"):
        if root_add!="":
            splitdir = Path(root_add) / split  # 相当于osp.join

            if not splitdir.is_dir():
                raise RuntimeError(f'Invalid directory "{root_add}"')

            splitdir_left = splitdir / "left"
            splitdir_right = splitdir / "right"

            self.left_list += sorted(glob.glob(os.path.join(splitdir_left, "*")))
            self.right_list += sorted(glob.glob(os.path.join(splitdir_right, "*")))

    def __getitem__(self, index):
        """
        Args:
            index (int): Index

        Returns:
            img: `PIL.Image.Image` or transformed `PIL.Image.Image`.
        """
        # img1 = Image.open(self.left_list[index]).convert('RGB')
        # img2 = Image.open(self.right_list[index]).convert('RGB')

        ###for root2
        if self.need_root2:
            if os.path.basename(self.left_list[index]) != os.path.basename(self.right_list[index]):
                print(self.left_list[index])
                raise ValueError("cannot compare pictures.")
            if os.path.basename(self.left_list[index]) != os.path.basename(self.right_list2[index]):
                print(self.left_list[index])
                raise ValueError("cannot compare pictures.root2!!")
            ##
            img1 = cv2.imread(self.left_list[index])
            img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
            img2 = cv2.imread(self.right_list[index])
            img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

            img1_root2 = cv2.imread(self.left_list2[index])
            img1_root2 = cv2.cvtColor(img1_root2, cv2.COLOR_BGR2RGB)
            img2_root2 = cv2.imread(self.right_list2[index])
            img2_root2 = cv2.cvtColor(img2_root2, cv2.COLOR_BGR2RGB)

            # random cut for pair
            H, W, _ = img1.shape
            # randint是闭区间
            # print(H)
            # print(W)
            # print(self.patch_size)
            ### 添加功能 支持多数据集同时训练和测试--2021/10/15
            # 超过大小自动改为图片真实大小
            # 仅本轮更改有效
            if self.patch_size[0] > H:
                temp_patch_size_0 = H
            else:
                temp_patch_size_0 = self.patch_size[0]
            if self.patch_size[1] > W:
                temp_patch_size_1 = W
            else:
                temp_patch_size_1 = self.patch_size[1]

            if temp_patch_size_0 == H:
                startH = 0
                startW = 0
            else:
                # print("not equal")
                # print(temp_patch_size_0)
                # print(H)
                # raise ValueError("why not equal?")
                startH = random.randint(0, H - temp_patch_size_0 - 1)
                startW = random.randint(0, W - temp_patch_size_1 - 1)

            ###
            # print(img1.shape)  #（512，512，3）
            # raise ValueError("stop utils")
            if self.need_H==True:
                try:
                    # 如果使用传统方法，应当在crop patches 之前
                    H_list = get_H(img1, img2)  # 可以忽略 这个是传统单应性获取的方法
                except:
                    print(os.path.basename(self.left_list[index]))
                    print("error h matrix")
                    raise ValueError("stop")
            else:
                H_list = ['None']
            img1 = img1[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]
            img2 = img2[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]

            img1_root2 = img1_root2[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]
            img2_root2 = img2_root2[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]


            # for homo 在上述patch基础上再进行缩放和裁剪 返回patch以及相应的corners
            homo_img1 = cv2.resize(img1, (self.homopic_size, self.homopic_size))
            homo_img2 = cv2.resize(img2, (self.homopic_size, self.homopic_size))
            homo_img1 = self.homotransforms(homo_img1)
            homo_img2 = self.homotransforms(homo_img2)
            homo_img1 = torch.mean(homo_img1, dim=0, keepdim=True)  # 转灰度
            homo_img2 = torch.mean(homo_img2, dim=0, keepdim=True)  # 转灰度

            homo_img1_root2 = cv2.resize(img1_root2, (self.homopic_size, self.homopic_size))
            homo_img2_root2 = cv2.resize(img2_root2, (self.homopic_size, self.homopic_size))
            homo_img1_root2 = self.homotransforms(homo_img1_root2)
            homo_img2_root2 = self.homotransforms(homo_img2_root2)
            homo_img1_root2 = torch.mean(homo_img1_root2, dim=0, keepdim=True)  # 转灰度
            homo_img2_root2 = torch.mean(homo_img2_root2, dim=0, keepdim=True)  # 转灰度


            # pick top left corner
            if self.homopic_size - self.rho - self.homopatch_size >= self.rho:
                x = random.randint(self.rho, self.homopic_size - self.rho - self.homopatch_size)
                y = random.randint(self.rho, self.homopic_size - self.rho - self.homopatch_size)
            else:
                x = 0
                y = 0
            # print(x,y)
            corners = torch.tensor(
                [
                    [x, y],
                    [x + self.homopatch_size, y],
                    [x + self.homopatch_size, y + self.homopatch_size],
                    [x, y + self.homopatch_size],
                ], dtype=torch.float32
            )
            homo_img1 = homo_img1[:, y: y + self.homopatch_size, x: x + self.homopatch_size]
            homo_img2 = homo_img2[:, y: y + self.homopatch_size, x: x + self.homopatch_size]

            homo_img1_root2 = homo_img1_root2[:, y: y + self.homopatch_size, x: x + self.homopatch_size]
            homo_img2_root2 = homo_img2_root2[:, y: y + self.homopatch_size, x: x + self.homopatch_size]

            ################## [homo_img1,homo_img2,corners]

            ##
            # if H_list[0] == None:
            #     print(self.left_list[index])
            #     print(self.right_list[index])
            #     raise ValueError("None!!H_matrix")
            #     # 只有ToTensor
            #     if self.transform:
            #         return self.transform(img1), self.transform(img2),self.transform(img1_root2), self.transform(img2_root2)  # ,H_list[1],H_list[2],H_list[3]
            #     return img1, img2,img1_root2,img2_root2  # ,H_list[1],H_list[2],H_list[3]

            # 只有ToTensor
            if self.transform:
                # return self.transform(img1),self.transform(img2),H_list[0] #,H_list[1],H_list[2],H_list[3]
                if self.need_file_name:
                    return self.transform(img1), self.transform(img2), H_list[0], os.path.basename(
                        self.left_list[index]), homo_img1, homo_img2, corners,self.transform(img1_root2), self.transform(img2_root2)  # ,H_list[1],H_list[2],H_list[3]
                else:
                    return self.transform(img1), self.transform(img2), H_list[
                        0], homo_img1, homo_img2, corners,self.transform(img1_root2), self.transform(img2_root2)  # ,H_list[1],H_list[2],H_list[3]

            if self.need_file_name:
                return img1, img2, H_list[0], os.path.basename(
                    self.left_list[index]), homo_img1, homo_img2, corners,img1_root2,img2_root2  # ,H_list[1],H_list[2],H_list[3]
            else:
                return img1, img2, H_list[0], homo_img1, homo_img2, corners,img1_root2,img2_root2  # ,H_list[1],H_list[2],H_list[3]

        ###end for root2

        if os.path.basename(self.left_list[index]) != os.path.basename(self.right_list[index]):
            print(self.left_list[index])
            raise ValueError("cannot compare pictures.")
        ##
        img1 = cv2.imread(self.left_list[index])
        img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
        img2 = cv2.imread(self.right_list[index])
        img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)
        #random cut for pair
        H, W, _ = img1.shape
        #randint是闭区间
        # print(H)
        # print(W)
        # print(self.patch_size)

        ### 添加功能 支持多数据集同时训练和测试--每次改动都要写两份，上面的if里一份--2021/10/15
        # 超过大小自动改为图片真实大小
        # 仅本轮更改有效
        if self.patch_size[0] > H:
            temp_patch_size_0 = H
        else:
            temp_patch_size_0 = self.patch_size[0]
        if self.patch_size[1] > W:
            temp_patch_size_1 = W
        else:
            temp_patch_size_1 = self.patch_size[1]

        #先计算H 添加功能 支持多数据集同时训练和测试--每次改动都要写两份，上面的if里一份--2021/10/15
        # print(img1.shape)  #（512，512，3）
        # raise ValueError("stop utils")
        if self.need_H==True:
            try:
                H_list = get_H(img1, img2)  # 可以忽略 这个是传统单应性获取的方法
            except:
                print(os.path.basename(self.left_list[index]))
                print("error h matrix")
                raise ValueError("stop")
        else:
            H_list = ['None']

        if temp_patch_size_0==H:
            startH = 0
            startW = 0
        else:
            # print("not equal")
            # print(temp_patch_size_0)
            # print(H)
            # raise ValueError("why not equal?")
            startH = random.randint(0,H-temp_patch_size_0-1)
            startW = random.randint(0,W-temp_patch_size_1-1)

        img1 = img1[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]
        img2 = img2[startH:(startH + temp_patch_size_0), startW:(startW + temp_patch_size_1)]

        #for homo 在上述patch基础上再进行缩放和裁剪 返回patch以及相应的corners
        homo_img1 = cv2.resize(img1,(self.homopic_size,self.homopic_size))
        homo_img2 = cv2.resize(img2, (self.homopic_size, self.homopic_size))
        homo_img1 = self.homotransforms(homo_img1)
        homo_img2 = self.homotransforms(homo_img2)
        homo_img1 = torch.mean(homo_img1, dim=0, keepdim=True)  # 转灰度
        homo_img2 = torch.mean(homo_img2, dim=0, keepdim=True)  # 转灰度

        # pick top left corner
        if self.homopic_size - self.rho - self.homopatch_size >= self.rho:
            x = random.randint(self.rho, self.homopic_size - self.rho - self.homopatch_size)
            y = random.randint(self.rho, self.homopic_size - self.rho - self.homopatch_size)
        else:
            x = 0
            y = 0
        # print(x,y)
        corners = torch.tensor(
            [
                [x, y],
                [x + self.homopatch_size, y],
                [x + self.homopatch_size, y + self.homopatch_size],
                [x, y + self.homopatch_size],
            ],dtype=torch.float32
        )
        homo_img1 = homo_img1[:, y: y + self.homopatch_size, x: x + self.homopatch_size]
        homo_img2 = homo_img2[:, y: y + self.homopatch_size, x: x + self.homopatch_size]
        ################## [homo_img1,homo_img2,corners]


        ##
        # if H_list[0]==None:
        #     print(self.left_list[index])
        #     print(self.right_list[index])
        #     raise ValueError("None!!H_matrix-363")
        #     # 只有ToTensor
        #     if self.transform:
        #         return self.transform(img1), self.transform(img2) # ,H_list[1],H_list[2],H_list[3]
        #     return img1, img2  # ,H_list[1],H_list[2],H_list[3]

        #只有ToTensor
        if self.transform:
            # return self.transform(img1),self.transform(img2),H_list[0] #,H_list[1],H_list[2],H_list[3]
            if self.need_file_name:
                return self.transform(img1), self.transform(img2), H_list[0], os.path.basename(self.left_list[index]),homo_img1,homo_img2,corners  # ,H_list[1],H_list[2],H_list[3]
            else:
                return self.transform(img1), self.transform(img2), H_list[0],homo_img1,homo_img2,corners  # ,H_list[1],H_list[2],H_list[3]

        if self.need_file_name:
            return img1, img2, H_list[0],os.path.basename(self.left_list[index]),homo_img1,homo_img2,corners  # ,H_list[1],H_list[2],H_list[3]
        else:
            return img1,img2,H_list[0],homo_img1,homo_img2,corners #,H_list[1],H_list[2],H_list[3]

    def __len__(self):
        return len(self.left_list)
