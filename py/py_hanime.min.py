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
	def __init__(A):super().__init__();A.debug=False;A.name=F;A.error_play_url='https://kjjsaas-sh.oss-cn-shanghai.aliyuncs.com/u/3401405881/20240818-936952-fc31b16575e80a7562cdb1f81a39c6b0.mp4';A.home_url='https://hanime1.me';A.headers={H:'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36'}
	def getName(A):return A.name
	def init(A,extend='{}'):A.extend=extend
	def getDependence(A):return[]
	def isVideoFormat(A,url):0
	def manualVideoCheck(A):0
	def homeContent(D,filter):B='泡麵番';A='type_id';C={'class':[{A:'裏番',E:'裏番'},{A:B,E:B}],'filters':{}};return C
	def homeVideoContent(A):return{B:[],C:0,D:0}
	def categoryContent(E,cid,page,filter,ext):
		H={B:[],C:0,D:0};O=E.home_url+f"/search?genre={parse.quote(cid)}&page={page}";M=E.get(O)
		if M:
			P=G(M)
			for F in P('div.home-rows-videos-wrapper a').items():
				N=F.attr('href')
				if E.home_url not in N:continue
				H[B].append({I:N.split('watch?v=')[-1],J:F('div.home-rows-videos-title').text(),'vod_pic':F('img').attr(L),K:A})
		return H
	def detailContent(L,did):G=did[0];H=[{E:A,I:G,J:A,K:A,'vod_year':A,'vod_area':A,'vod_actor':A,'vod_director':A,'vod_content':A,'vod_play_from':F,'vod_play_url':'01$'+G}];return{B:H,C:0,D:0}
	def searchContent(A,key,quick,page='1'):E=f"{A.home_url}/search?k={key}&page={page}&os=pc";F=[];return{B:[],C:0,D:0}
	def playerContent(E,flag,pid,vipFlags):
		B='url';A={B:[],C:0,D:0,'header':{H:'okhttp/5.0.0'}};F=E.get(E.home_url+'/watch?v='+pid)
		if F:
			J=G(F)
			for I in J('video source').items():K=I.attr('size');M=I.attr(L);A[B].append(K);A[B].append(M)
		return A
	def localProxy(A,params):0
	def destroy(A):return'正在Destroy'
	def get(A,url):
		try:B=urllib.request.Request(url,headers=A.headers,method='GET');C=urllib.request.urlopen(B);D=C.read().decode('utf-8');return D
		except Exception as E:print(f"Error in get: {E}")
if __name__=='__main__':0
