# howto run 

- not possible for python3
  

```
sudo python ping.py
```


```
1.  sudo python ping.py

   아래 2개의 입력값을 문는데,
    - Please input timeout to wait for ping response (unit: ms) : 2   
     --> 난 2 로만 해봤음.
    - Please input the number of count to ping : 100
       --> 가능한 10000 정도 돌려보면 좋을 듯 (퇴근전에 돌려놓고 퇴근)
     
    결과로, ping100 이라는 파일이 생성 (100을 입력했을때)
     
2. 평균 및 그래프 등을 보기 위한 분석을 위해서.
     python3 plot_from_file.py   (요건 python v3 )
   --> 평균, 표준편차 등등 나옴.
   --> main 함수에서 이것 저것 comment를 풀면 그래프로 볼 수도 있음.
```
