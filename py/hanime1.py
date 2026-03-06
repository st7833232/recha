#!/usr/bin/python3
# -*- coding: utf-8 -*-
# @Author  : Doubebly
# @Time    : 2026/3/3
# @file    : py_hanime.min.py

L='src'
K='vod_remarks'
J='vod_name'
I='vod_id'
H='User-Agent'
F='hanime'
E='type_name'
D='jx'
C='parse'
B='list'
A=''
import sys,urllib.request
from pyquery import PyQuery as G
from urllib import parse
sys.path.append('..')
from base.spider import Spider as M

class Spider(M):
    def __init__(A):
        super().__init__()
        A.debug=False
        A.name=F
        A.error_play_url='https://kjjsaas-sh.oss-cn-shanghai.aliyuncs.com/u/3401405881/20240818-936952-fc31b16575e80a7562cdb1f81a39c6b0.mp4'
        A.home_url='https://hanime1.me'
        A.headers={H:'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36'}

    def getName(A):
        return A.name

    def init(A,extend='{}'):
        A.extend=extend

    def getDependence(A):
        return[]

    def isVideoFormat(A,url):
        return False

    def manualVideoCheck(A):
        return False

    def homeContent(D,filter):
        # 只添加分类，不加筛选
        classes = [
            {'type_id': '裏番', 'type_name': '裏番'},
            {'type_id': '泡麵番', 'type_name': '泡麵番'},
            {'type_id': 'Motion Anime', 'type_name': 'Motion Anime'},
            {'type_id': '3DCG', 'type_name': '3DCG'},
            {'type_id': '2D動畫', 'type_name': '2D動畫'},
            {'type_id': 'AI生成', 'type_name': 'AI生成'},
            {'type_id': 'MMD', 'type_name': 'MMD'},
            {'type_id': 'Cosplay', 'type_name': 'Cosplay'},
        ]
        # 保持原有的filters为空
        filters = {}
        return {'class': classes, 'filters': filters}

    def homeVideoContent(A):
        # 完全保持原有的首页内容逻辑
        return {B:[], C:0, D:0}

    def categoryContent(E, cid, page, filter, ext):
        # 完全保持原有的URL构建方式，不加任何排序参数
        O = E.home_url + f"/search?genre={parse.quote(cid)}&page={page}"
        M = E.get(O)
        result = {B:[], C:0, D:0}
        
        if M:
            P = G(M)
            # 保持原有的解析方式
            for F in P('div.home-rows-videos-wrapper a').items():
                N = F.attr('href')
                if E.home_url not in N:
                    continue
                result[B].append({
                    I: N.split('watch?v=')[-1],
                    J: F('div.home-rows-videos-title').text(),
                    'vod_pic': F('img').attr(L),
                    K: A
                })
            # 保持原有的分页逻辑
            result[C] = page
            result[D] = page + 1
        return result

    def detailContent(L, did):
        # 完全保持原有的详情页逻辑
        G = did[0]
        H = [{
            E: A,
            I: G,
            J: A,
            K: A,
            'vod_year': A,
            'vod_area': A,
            'vod_actor': A,
            'vod_director': A,
            'vod_content': A,
            'vod_play_from': F,
            'vod_play_url': '01$' + G
        }]
        return {B: H, C:0, D:0}

    def searchContent(A, key, quick, page='1'):
        # 完全保持原有的搜索逻辑
        E = f"{A.home_url}/search?k={key}&page={page}&os=pc"
        F = []
        return {B:[], C:0, D:0}

    def playerContent(E, flag, pid, vipFlags):
        # 完全保持原有的播放逻辑
        B='url'
        A = {B:[], C:0, D:0, 'header':{H:'okhttp/5.0.0'}}
        F = E.get(E.home_url+'/watch?v='+pid)
        
        if F:
            J = G(F)
            for I in J('video source').items():
                K = I.attr('size')
                M = I.attr(L)
                A[B].append(K)
                A[B].append(M)
        return A

    def localProxy(A, params):
        return None

    def destroy(A):
        return '正在Destroy'

    def get(A, url):
        try:
            B = urllib.request.Request(url, headers=A.headers, method='GET')
            C = urllib.request.urlopen(B, timeout=15)
            D = C.read().decode('utf-8', errors='ignore')
            return D
        except Exception as E:
            print(f"Error in get: {E}")
            return None

if __name__=='__main__':
    pass