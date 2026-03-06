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
        # 合并第二个spider的完整分类
        classes = [
            {'type_id': '裏番', 'type_name': '裏番'},
            {'type_id': '泡麵番', 'type_name': '泡麵番'},
            {'type_id': 'Motion Anime', 'type_name': 'Motion Anime'},
            {'type_id': '3DCG', 'type_name': '3DCG'},
            {'type_id': '2D動畫', 'type_name': '2D動畫'},
            {'type_id': 'AI生成', 'type_name': 'AI生成'},
            {'type_id': 'MMD', 'type_name': 'MMD'},
            {'type_id': 'Cosplay', 'type_name': 'Cosplay'},
            {'type_id': 'latest_rank', 'type_name': '最新上市'},
            {'type_id': 'daily_rank', 'type_name': '本日排行'},
            {'type_id': 'weekly_rank', 'type_name': '本週排行'},
            {'type_id': 'monthly_rank', 'type_name': '本月排行'}
        ]
        
        # 添加排序筛选选项
        sort_options = [
            {"n": "最新上市", "v": "最新上市"},
            {"n": "最新上傳", "v": "最新上傳"},
            {"n": "本日排行", "v": "本日排行"},
            {"n": "本週排行", "v": "本週排行"},
            {"n": "本月排行", "v": "本月排行"},
            {"n": "觀看次數", "v": "觀看次數"}
        ]
        
        filters = {}
        for item in classes:
            filters[item['type_id']] = [{"key": "sort", "name": "排序", "value": sort_options}]
            
        return {'class': classes, 'filters': filters}

    def homeVideoContent(A):
        # 获取首页内容（最新视频）- 保持原有的首页逻辑
        return {B:[], C:0, D:0}

    def categoryContent(E, cid, page, filter, ext):
        # 获取排序参数
        sort = ext.get('sort', '最新上市') if ext else '最新上市'
        
        # 根据分类类型构建URL
        if 'rank' in cid or cid == 'latest_rank':
            rank_map = {'latest_rank': '最新上市', 'daily_rank': '本日排行', 'weekly_rank': '本週排行', 'monthly_rank': '本月排行'}
            url = f"{E.home_url}/search?sort={parse.quote(rank_map.get(cid, '最新上市'))}&page={page}"
        else:
            url = f"{E.home_url}/search?genre={parse.quote(cid)}&sort={parse.quote(sort)}&page={page}"
        
        M = E.get(url)
        result = {B:[], C:0, D:0}
        
        if M:
            P = G(M)
            # 保持原有的PyQuery解析方式
            for F in P('div.home-rows-videos-wrapper a').items():
                N = F.attr('href')
                if E.home_url not in N:
                    continue
                # 保持原有的数据格式
                result[B].append({
                    I: N.split('watch?v=')[-1],
                    J: F('div.home-rows-videos-title').text(),
                    'vod_pic': F('img').attr(L),
                    K: A  # 保持原有的remarks为空
                })
            
            # 尝试获取总页数
            try:
                # 通过PyQuery查找分页信息
                page_text = P('.pagination').text()
                if page_text:
                    import re
                    pages = re.findall(r'/(\d+)', page_text)
                    if pages:
                        result[D] = int(pages[-1])
                    else:
                        result[D] = page + 1
                else:
                    result[D] = page + 1
            except:
                result[D] = page + 1
            
            result[C] = page
            
        return result

    def detailContent(L, did):
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
        # 实现搜索功能
        url = f"{A.home_url}/search?k={key}&page={page}&os=pc"
        M = A.get(url)
        result = {B:[], C:0, D:0}
        
        if M:
            P = G(M)
            for F in P('div.home-rows-videos-wrapper a').items():
                N = F.attr('href')
                if A.home_url not in N:
                    continue
                result[B].append({
                    I: N.split('watch?v=')[-1],
                    J: F('div.home-rows-videos-title').text(),
                    'vod_pic': F('img').attr(L),
                    K: A
                })
            
            result[C] = int(page)
            result[D] = int(page) + 1  # 简化处理，实际可能需要解析总页数
            
        return result

    def playerContent(E, flag, pid, vipFlags):
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