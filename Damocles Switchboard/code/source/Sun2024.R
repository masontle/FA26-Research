######## Damocles' Switchboard: Information Externalities And the Autocratic Logic of Internet Control ########
######## Meicen Sun ########

###### Analyses ######

require(PanelMatch) # install_github("insongkim/PanelMatch", dependencies=TRUE, ref = "se_comparison")
require(dplyr)
require(readr)
require(ggplot2)
require(stringr)
require(boot)
require(readxl)
require(fixest)
require(lmtest)
require(data.table)
require(stargazer)

#### I. PanelMatch analysis ####

## HK, North America, Shanghai-Shenzhen firm data
h<-read.csv("hk8719.csv")
na<-read.csv("na.csv")
ss<-read.csv("ss.csv")

h$date<-as.character(as.Date(as.character(h$datadate),"%Y%m%d"))
na$date<-as.character(as.Date(as.character(na$datadate),"%Y%m%d"))
ss$date<-as.character(as.Date(as.character(ss$datadate),"%Y%m%d"))

## Exchange rate data (CNY, HKD, SGD to USD):
forex<-read.csv("exchange_rates.csv")
exch<-cbind(date=as.character((forex[,1])),ca=as.numeric(as.character((forex$CANADA....SPOT.EXCHANGE.RATE..CANADIAN...US..))), cn=as.numeric(as.character((forex$CHINA....SPOT.EXCHANGE.RATE..YUAN.US..P.R..))),sg=as.numeric(as.character(forex$SINGAPORE....SPOT.EXCHANGE.RATE..SINGAPORE...US..)),hk=as.numeric(as.character((forex$HONG.KONG....SPOT.EXCHANGE.RATE..HK..US..))))[6:12073,]
## Merge with main datasets:
hnew<-merge(h,exch,by=c("date"))
nanew<-merge(na,exch,by=c("date"))
ssnew<-merge(ss,exch,by=c("date"))
nanew$ca<-as.numeric(nanew$ca)
ssnew$cn<-as.numeric(ssnew$cn)
hnew$cn<-as.numeric(hnew$cn)
hnew$hk<-as.numeric(hnew$hk)
hnew$sg<-as.numeric(hnew$sg)

## Exchange-rate-adjusted quarterly revenue
ssnew$rev<-ifelse(ssnew$curcdq=="USD",ssnew$revtq,(ssnew$revtq)/(ssnew$cn))
nanew$rev<-ifelse(nanew$curcdq=="USD",nanew$revtq,(nanew$revtq)/(nanew$ca))
hnew$rev<-ifelse(hnew$curcdq=="USD",hnew$revtq,ifelse(hnew$curcdq=="CNY",(hnew$revtq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$revtq)/(hnew$hk),(hnew$revtq)/(hnew$sg))))

## Repeat for variables with < 1/3 NA's for China & US
ssnew$at<-ifelse(ssnew$curcdq=="USD",ssnew$atq,(ssnew$atq)/(ssnew$cn))
nanew$at<-ifelse(nanew$curcdq=="USD",nanew$atq,(nanew$atq)/(nanew$ca))
hnew$at<-ifelse(hnew$curcdq=="USD",hnew$atq,ifelse(hnew$curcdq=="CNY",(hnew$atq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$atq)/(hnew$hk),(hnew$atq)/(hnew$sg))))
ssnew$che<-ifelse(ssnew$curcdq=="USD",ssnew$cheq,(ssnew$cheq)/(ssnew$cn))
nanew$che<-ifelse(nanew$curcdq=="USD",nanew$cheq,(nanew$cheq)/(nanew$ca))
hnew$che<-ifelse(hnew$curcdq=="USD",hnew$cheq,ifelse(hnew$curcdq=="CNY",(hnew$cheq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$cheq)/(hnew$hk),(hnew$cheq)/(hnew$sg))))
ssnew$cstk<-ifelse(ssnew$curcdq=="USD",ssnew$cstkq,(ssnew$cstkq)/(ssnew$cn))
nanew$cstk<-ifelse(nanew$curcdq=="USD",nanew$cstkq,(nanew$cstkq)/(nanew$ca))
hnew$cstk<-ifelse(hnew$curcdq=="USD",hnew$cstkq,ifelse(hnew$curcdq=="CNY",(hnew$cstkq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$cstkq)/(hnew$hk),(hnew$cstkq)/(hnew$sg))))
ssnew$lse<-ifelse(ssnew$curcdq=="USD",ssnew$lseq,(ssnew$lseq)/(ssnew$cn))
nanew$lse<-ifelse(nanew$curcdq=="USD",nanew$lseq,(nanew$lseq)/(nanew$ca))
hnew$lse<-ifelse(hnew$curcdq=="USD",hnew$lseq,ifelse(hnew$curcdq=="CNY",(hnew$lseq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$lseq)/(hnew$hk),(hnew$lseq)/(hnew$sg))))
ssnew$lt<-ifelse(ssnew$curcdq=="USD",ssnew$ltq,(ssnew$ltq)/(ssnew$cn))
nanew$lt<-ifelse(nanew$curcdq=="USD",nanew$ltq,(nanew$ltq)/(nanew$ca))
hnew$lt<-ifelse(hnew$curcdq=="USD",hnew$ltq,ifelse(hnew$curcdq=="CNY",(hnew$ltq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$ltq)/(hnew$hk),(hnew$ltq)/(hnew$sg))))
ssnew$seq<-ifelse(ssnew$curcdq=="USD",ssnew$seqq,(ssnew$seqq)/(ssnew$cn))
nanew$seq<-ifelse(nanew$curcdq=="USD",nanew$seqq,(nanew$seqq)/(nanew$ca))
hnew$seq<-ifelse(hnew$curcdq=="USD",hnew$seqq,ifelse(hnew$curcdq=="CNY",(hnew$seqq)/(hnew$cn),ifelse(hnew$curcdq=="HKD",(hnew$seqq)/(hnew$hk),(hnew$seqq)/(hnew$sg))))

ssnew$loc<-as.character(ssnew$loc)
hnew$loc<-as.character(hnew$loc)
nanew$loc<-as.character(nanew$loc)

## Extract relevant variables (date, rev, at, che, cstk, lse, lt, seq, NAICS, gvkey,location):
china<-data.frame(date=ssnew$date,rev=ssnew$rev,at=ssnew$at, che=ssnew$che, cstk=ssnew$cstk, lse=ssnew$lse, lt=ssnew$lt, seq=ssnew$seq, naics=ssnew$naics,gvkey=ssnew$gvkey,loc=ssnew$loc)
hongkong<-data.frame(date=hnew$date,rev=hnew$rev,at=hnew$at, che=hnew$che, cstk=hnew$cstk, lse=hnew$lse, lt=hnew$lt, seq=hnew$seq, naics=hnew$naics,gvkey=hnew$gvkey,loc=hnew$loc)
namerica<-data.frame(date=nanew$date,rev=nanew$rev,at=nanew$at, che=nanew$che, cstk=nanew$cstk, lse=nanew$lse, lt=nanew$lt, seq=nanew$seq, naics=nanew$naics,gvkey=nanew$gvkey,loc=nanew$loc)
## Combine three datasets:
d<-rbind(china,hongkong,namerica)
d$date<-as.Date(d$date)
d$rev<-as.numeric(as.character(d$rev))
d$loc<-as.character(d$loc)

## Post-1999 Chinese & US data:
d<-subset(d,d$date>"1999-12-31")
c<-subset(d,d$loc=="CHN")
u<-subset(d,d$loc=="USA")

## Keep obs for 4 standard quarterly dates
date.list<-c("03-31","06-30","09-30","12-31")
pat=paste(date.list,collapse="|")
c<-c[grep(pat, c$date), ]
u<-u[grep(pat, u$date), ]

## Trim 2010-12-31 for China due to NAs
c<-subset(c,c$date!="2010-12-31")

c$naics<-as.factor(c$naics)

#### Data-intensity determination method 1

## KPSS data:
kpss<-read.csv("patents_xi.csv")
## ID data-intensive patent classes based on art unit key word search ("data"): https://www.uspto.gov/patents-application-process/patent-search/understanding-patent-classifications/patent-classification
## 1. ID technology classes with data-intensive subclasses:
data.class<-c("702","703","700","706","715","707","710","717","709","704","341","705","701")
## 2. Verify against USPC class schedule that all subclasses of all classes above are data-intensive (https://www.uspto.gov/web/patents/classification/, except Subclasses 231-244 missing from art unit list)
## Thus designate all obs in all classes above as data-intensive and create data-intensity variable:
kpss$data<-ifelse(kpss$class %in% data.class,1,0)
## US and Chinese NASDAQ & NYSE stock data:
nasdaq<-read.csv("NASDAQ.csv")
nyse<-read.csv("NYSE.csv")
## Subset 2009 data for matching on firm name and combine datasets:
nasdaq09<-subset(nasdaq,nasdaq$date=="20090930")
nyse09<-subset(nyse,nyse$date=="20090930")
stock09<-rbind(nasdaq09,nyse09)
## Merge with KPSS on firm permno:
kpss$PERMNO<-kpss$permno
d5<-merge(kpss,stock09,by=c("PERMNO"),all=TRUE)
## Extract data-intensive obs:
di5<-subset(d5,d5$data=="1")
## Plot absolute frequency of data-intensive patents by NAICS:
barplot(table(di5$NAICS),las=2,cex.axis=1.5,cex.lab=2) 
## Vector of data-intensive non-NA NAICS codes based on plot:
art.naics<-unique(na.omit(di5$NAICS))
## Frequency table for data-intensive NAICS codes:
tab1<-as.data.frame(table(di5$NAICS))
## Table for data-intensive NAICS codes:
di5.naics<-subset(d5,d5$NAICS %in% art.naics)
tab2<-as.data.frame(table(di5.naics$NAICS))
## Merge two tables:
art.tab<-merge(tab1,tab2,by=c("Var1"))
## Variable for % of data-intensive patents for each NAICS:
art.tab$pct<-art.tab$Freq.x/art.tab$Freq.y
## Variable for NAICS descriptions:
art.tab$Name<-c("211111: Crude petro & ant gas extr","221112: Fossil fuel electric power gen","324110: Petro refineries","325110: Petrochem manufacturing","331312: Primary alum prod","334413: Semiconductor manufacturing","454111: Electronic shopping","517110: Wired telecom carriers","517210: Wireless telecom carriers","518210: Data processing/hosting","519130: Internet publishing/broadcast/web search","524113: Direct life inusrance carriers","541612: HR consulting services")
## Barplot data-intensive percentages:
bar1<-barplot(art.tab$pct,ylab="Ratio of data-intensive patents",cex.axis=1.5)
axis(1, at=bar1, labels=art.tab$Var1, las=2, cex.axis=1.5, cex.lab=2,ylab="Ratio of data-intensive patents") # replicates Table A1
## Set two levels of data-intensity based on % in art.tab: All, >median:
pat.di.all<-c("211111","221112","324110","325110","331312","334413","454111","517110","517210","518210","519130","524113","541612")
pat.di..1<-c("454111","517110","518210","519130","524113","541612")
pat.di.all<-as.factor(pat.di.all)
pat.di..1<-as.factor(pat.di..1)

#### Data-intensity determination method 2
## Alternative data-intensity designation based on "Internet" keyword search in 2012 NAICS codes: https://www.census.gov/cgi-bin/sssd/naics/naicsrch 
naics.treat<-as.numeric(c("454111","454112","511110","511120","511130","511140","511191","511199","515112","517110","517210","517919","519130","541511","561422")) # replicates Table A2

## Assign treatment based on two levels of patent-based data-intensity scores:
c$t1<-ifelse(c$naics %in% pat.di.all & c$date>"2014-05-31",1,0)
c$t2<-ifelse(c$naics %in% pat.di..1 & c$date>"2014-05-31",1,0)
## Assign alternative treatment:
c$t5<-ifelse(c$naics %in% naics.treat & c$date>"2014-05-31",1,0)

## Trim duplicates by date+gvkey:
ctrim<-c[!duplicated(c[c(1,10)]),]
## Replace negative revenue & liabilities with NAs:
ctrim$rev <- replace(ctrim$rev, which(ctrim$rev < 0), NA)
ctrim$lt <- replace(ctrim$lt, which(ctrim$lt < 0), NA)

ctrim$rev<-log(ctrim$rev+0.001)
ctrim$at<-log(ctrim$at+0.001)
ctrim$lt<-log(ctrim$lt+0.001)

## Date variable for PanelMatch
pm.date<-data.frame(date=unique(ctrim$date),Date=c(1:48))
ctrim<-merge(ctrim,pm.date,by=c("date"))

## Assign false treatment date (2008-06-30)
ctrim$p1<-ifelse(ctrim$naics %in% pat.di.all & ctrim$date>"2008-06-29",1,0)
ctrim$p2<-ifelse(ctrim$naics %in% pat.di..1 & ctrim$date>"2008-06-29",1,0)
ctrim$p5<-ifelse(ctrim$naics %in% naics.treat & ctrim$date>"2008-06-29",1,0)

## Assign pretrend test date (2012-03-01)
ctrim$t1p<-ifelse(ctrim$naics %in% pat.di.all & ctrim$date>"2012-02-28",1,0)

## Determine number of max. matches
## Largest subset of control firms:
ctrim.control<-subset(ctrim,!ctrim$naics %in% pat.di..1)
## Number of unique gvkeys for each period:
unique.controls.by.date <- ctrim.control %>% group_by(date) %>% summarize(count = n_distinct(gvkey))
print(unique.controls.by.date,n=48)
## Thus largest number pre-treatment: 4003 (2013-12-31)

set.seed(2023)

## PM results & robustness checks
## Main result (Mahalanobis, max matches)
pm.t1mm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "t1", refinement.method = "mahalanobis",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
t1mm<- PanelEstimate(sets = pm.t1mm,
                     data = ctrim)
plot(t1mm,main="",cex.lab=1.5,ylim=c(-0.15,0.5),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue") # replicates Fig 4

## False date test (2008-06-30)
pm.p1mm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "p1", refinement.method = "mahalanobis",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
p1mm<- PanelEstimate(sets = pm.p1mm,
                     data = ctrim)
plot(p1mm,main="Average Treatment Effect (False Date)",cex.main=2,cex.lab=1.5,xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue",ylim=c(-0.6,0.15)) # replicates Fig A2

## Pretrend test (Mahalanobis, max matches)
pm.t1mm.p<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                       treatment = "t1p", refinement.method = "mahalanobis",
                       data = ctrim, match.missing = T,
                       covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                       size.match = 4003, qoi = "att" ,outcome.var = "rev",
                       lead = 0:10, forbid.treatment.reversal = FALSE)
t1mm.p<- PanelEstimate(sets = pm.t1mm.p,
                       data = ctrim)
plot(t1mm.p,main="Pretrend Test",cex.main=2,cex.lab=1.5,ylim=c(-0.3,0.4),xlab="Quarters before treatment administration",ylab="Estimated treatment effect on revenue") # replicates Fig A4

# Six panels in Fig A3 replicated below
## 20 max matches robustness
pm.t1mm20<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                       treatment = "t1", refinement.method = "mahalanobis",
                       data = ctrim, match.missing = T,
                       covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                       size.match = 20, qoi = "att" ,outcome.var = "rev",
                       lead = 0:10, forbid.treatment.reversal = FALSE)
t1mm20<- PanelEstimate(sets = pm.t1mm20,
                       data = ctrim)
plot(t1mm20,main="Average Treatment Effect (20 max. matches)",cex.main=2,cex.lab=1.5,ylim=c(-0.15,0.5),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## > median data-intensity robustness
pm.t2mm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "t2", refinement.method = "mahalanobis",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
t2mm<- PanelEstimate(sets = pm.t2mm,
                     data = ctrim)
plot(t2mm,main="Average Treatment Effect (>median data-intensity)",cex.main=2,cex.lab=1.5,ylim=c(-0.2,0.9),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## Alt. data-intensity robustness
pm.t5mm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "t5", refinement.method = "mahalanobis",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
t5mm<- PanelEstimate(sets = pm.t5mm,
                     data = ctrim)
plot(t5mm,main="Average Treatment Effect (alt. data-intensity)",cex.main=2,cex.lab=1.5,ylim=c(-0.2,0.7),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## PS matching robustness
pm.t1pm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "t1", refinement.method = "ps.match",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
t1pm<- PanelEstimate(sets = pm.t1pm,
                     data = ctrim)
plot(t1pm,main="Average Treatment Effect (PS Matching)",cex.main=2,cex.lab=1.5,ylim=c(-0.15,0.5),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## CBPS robustness
pm.t1cbpm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                       treatment = "t1", refinement.method = "CBPS.match",
                       data = ctrim, match.missing = T,
                       covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                       size.match = 4003, qoi = "att" ,outcome.var = "rev",
                       lead = 0:10, forbid.treatment.reversal = FALSE)
t1cbpm<- PanelEstimate(sets = pm.t1cbpm,
                       data = ctrim)
plot(t1cbpm,main="Average Treatment Effect (CBPS Matching)",cex.main=2,cex.lab=1.5,ylim=c(-0.15,0.5),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## PS weighting robustness
pm.t1pw<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                     treatment = "t1", refinement.method = "ps.weight",
                     data = ctrim, match.missing = T,
                     covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                     size.match = 4003, qoi = "att" ,outcome.var = "rev",
                     lead = 0:10, forbid.treatment.reversal = FALSE)
t1pw<- PanelEstimate(sets = pm.t1pw,
                     data = ctrim)
plot(t1pw,main="Average Treatment Effect (PS Weighting)",cex.main=2,cex.lab=1.5,ylim=c(-0.15,0.5),xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

## Placebo loop test of difference between randomly drawn non-data-intensive obs, 30 iterations # replicates Fig A5
## Subset non-data-intensive obs:
ctrim.placebo<-subset(ctrim,!(ctrim$naics %in% pat.di.all))
## Number of unique gvkeys in treated sample:
ctrim.treated<-subset(ctrim,ctrim$naics %in% pat.di.all)
length(unique(ctrim.treated$gvkey)) # n=216
## Draw unique gvkeys equal in number to unique treated gvkeys as placeo sample:
placebo.samp<-as.numeric(sample((unique(ctrim.placebo$gvkey)),216))
## Assign placebo treatment for this sample (2014-06-01):
ctrim$placebo2<-ifelse(ctrim$gvkey %in% placebo.samp & ctrim$date>"2014-05-31",1,0)
## Rerun Mahalanobis matching for 30 loops and store point estimates:
placebo.est.set<-matrix(ncol=11,nrow=30)
for (i in 1:30){placebo.samp<-as.numeric(sample((unique(ctrim.placebo$gvkey)),216))
ctrim$placebo2<-ifelse(ctrim$gvkey %in% placebo.samp & ctrim$date>"2014-05-31",1,0)
pm.placebo2.mm<- PanelMatch(lag = 10, time.id = "Date", unit.id = "gvkey",
                            treatment = "placebo2", refinement.method = "mahalanobis",
                            data = ctrim, match.missing = T,
                            covs.formula = ~ I(lag(at, 1:10)) + I(lag(rev, 1:10) +I(lag(lt, 1:10))),
                            size.match = 4003, qoi = "att" ,outcome.var = "rev",
                            lead = 0:10, forbid.treatment.reversal = FALSE)
placebo2.mm<- PanelEstimate(sets = pm.placebo2.mm,
                            data = ctrim)
## Extract PM point estimates:
placebo.est.set[i,]<-placebo2.mm[[1]]}
## Mean from 30 iterations:
placebo.est.mean<-colMeans(placebo.est.set)
## Bootstrapped SEs for each mean using 500 iterations:
boot.set<-matrix(ncol=11,nrow=500)
calc.mean<- function(x,i){mean(x[i])}
for (i in 1:ncol(placebo.est.set)){boot.run<-boot(placebo.est.set[,i],calc.mean,500)
boot.set[,i]<-boot.run$t}
## Make plot for averaged point estimates & SEs:
placebo2.mm[[1]]<-placebo.est.mean
placebo2.mm[[2]]<-boot.set
plot(placebo2.mm,main="Average Treatment Effect (Non-uptaking, 30 loops)",cex.main=2,cex.lab=1.5,ylim=c(-0.2,0.2),xaxt = "n",xlab="Quarters since treatment administration",ylab="Estimated treatment effect on revenue")

#### II. DDD analysis ####

## US and Chinese data from firm dataset:
dnew<-subset(d,d$loc %in% c("USA","CHN"))
## Assign patent-based data-intensity:
dnew$treat<-ifelse(dnew$naics %in% pat.di.all,1,0)
## Assign >median data-intensity:
dnew$treat2<-ifelse(dnew$naics %in% pat.di..1,1,0)
## Assign alt. data-intensity: 
dnew$treat1<-ifelse(dnew$naics %in% naics.treat,1,0)

## China dummy:
dnew$china<-ifelse(dnew$loc=="CHN",1,0)
## Treatment dummy:
dnew$censor<-ifelse(dnew$date>"2014-05-31",1,0)

## Trim duplicates by date+gvkey:
dnew<-dnew[!duplicated(dnew[c(1,10)]),]
## Replace negative variables with NAs:
dnew$rev <- replace(dnew$rev, which(dnew$rev < 0), NA)
dnew$at<-replace(dnew$at,which(dnew$at <0),NA)
dnew$lt <- replace(dnew$lt, which(dnew$lt < 0), NA)
dnew$che <- replace(dnew$che, which(dnew$che < 0), NA)
dnew$cstk <- replace(dnew$cstk, which(dnew$cstk < 0), NA)
dnew$seq <- replace(dnew$seq, which(dnew$seq < 0), NA)
dnew$lse <- replace(dnew$lse, which(dnew$lse < 0), NA)

dnew$logrev<-log(dnew$rev+0.01)
dnew$logat<-log(dnew$at+0.01)
dnew$loglt<-log(dnew$lt+0.01)
dnew$logche<-log(dnew$che+0.01)
dnew$logcstk<-log(dnew$cstk+0.01)
dnew$logseq<-log(dnew$seq+0.01)
dnew$loglse<-log(dnew$lse+0.01)

## Year variable:
dnew$year<-substr(dnew$date, start = 1, stop = 4)
## Post-2010 data:
dnew<-subset(dnew,dnew$date>"2010-12-31")

## Remove obs with missing NAICS
dnew.naics<-dnew[!is.na(dnew$naics),]

dnew.naics$naics<-as.factor(dnew.naics$naics)
dnew.naics$year<-as.factor(dnew.naics$year)
dnew<-dnew.naics

## Summary statistics for Chinese firms in 2013
dnew.cn.treat<-subset(dnew,dnew$china=="1" & dnew$treat=="1" & dnew$year == "2013")
dnew.cn.control<-subset(dnew,dnew$china=="1" & dnew$treat=="0" & dnew$year == "2013")
## Keep 4 standard dates as for PM:
dnew.cn.treat<-dnew.cn.treat[grep(pat, dnew.cn.treat$date), ]
dnew.cn.control<-dnew.cn.control[grep(pat, dnew.cn.control$date), ]
stargazer(dnew.cn.treat) # replicates Table A3
stargazer(dnew.cn.control) # replicates Table A4
## T-test for main variables # replicates Table A5
t.test(dnew.cn.treat$logrev,dnew.cn.control$logrev)
t.test(dnew.cn.treat$logat,dnew.cn.control$logat)
t.test(dnew.cn.treat$logche,dnew.cn.control$logche)
t.test(dnew.cn.treat$logcstk,dnew.cn.control$logcstk)
t.test(dnew.cn.treat$loglt,dnew.cn.control$loglt)
t.test(dnew.cn.treat$logseq,dnew.cn.control$logseq)

## DDD with industry-clustered SEs
## Naive
ddd1<-feglm(logrev~treat*china*censor|year,dnew)
ddd2<-feglm(logrev~treat1*china*censor|year,dnew)
ddd3<-feglm(logrev~treat2*china*censor|year,dnew)
etable(ddd1,ddd3,ddd2,cluster=~naics,tex=TRUE) # replicates Table A7

## Saturated
ddd4<-feglm(logrev~treat*china*censor+logat+loglt|year,dnew)
ddd5<-feglm(logrev~treat1*china*censor+logat+loglt|year,dnew)
ddd6<-feglm(logrev~treat2*china*censor+logat+loglt|year,dnew)
etable(ddd4,ddd6,ddd5,cluster=~naics,tex=TRUE) # replicates Table A8

#### III. Citation analysis ####

## Assign knowledge-intensity based on references per page
## Reference data ("RPP2010" dataset):
rpp<-do.call(rbind,lapply(list.files(),read_excel))
nrow(rpp)
## Total references by discipline:
totalref<-aggregate(rpp$`Cited Reference Count`,by=list(rpp$`Research Areas`),FUN=sum)
## Total pages by discipline:
totalpage<-aggregate(rpp$`Number of Pages`, by=list(rpp$`Research Areas`), FUN=sum)
## Merge two datasets:
rpp<-merge(totalref,totalpage,by=c("Group.1"))
names(rpp)[1]<-'Research Areas'
## Variable for RP:
rpp$rp<-rpp$x.x/rpp$x.y
## Plot logged RP # replicates Fig A1
shortfield<-c("Agriculture","Astro&Astro","Biochem&Mol bio","Biz&Econ","Cardio sys&Cardio", "Cell bio","Chemistry","Comp sci","Endo&Metabolism","Engineering","Env sci&Eco","Gastro&Hep","Gen&Int med","Geochem&Geophy","Geology","Hematology","Immunology","Materials sci","Mathematics","Neuro&Neuro","Oncology","Optics","Pharma&Pharma","Physics","Plant sci","Polymer sci","Psychiatry","Psychology","PEO health","S&T other","Surgery")
par(mar=c(5.1, 4.5, 4.1, 2.1))
rpbar<-barplot(log(rpp$rp),ylab="Logged references per page",cex.lab=2,xaxt='n')
axis(1,at=rpbar,labels=FALSE)
text(x=rpbar,y=par("usr")[3]-0.07,labels=shortfield,xpd=NA,adj=1,srt=45,cex=0.7)

## Chinese research article data for 31 disciplines 2011-20
## ("CN0020" dataset)
file_list<-list.files()
cncite <- data.frame()
for (i in 1:length(file_list)){
  temp_data <- read.delim(file_list[i])
  temp_data$`Research Areas` <- gsub(".txt","",file_list[i])
  cncite <- rbind(cncite, temp_data)
}
file_list<-gsub(".txt","",file_list)
cncite<-subset(cncite,as.numeric(cncite$PY) %in% c(2011:2020))
## ("CN1120new" dataset)
file_list2<-list.files()
cncitenew <- data.frame()
for (i in 1:length(file_list2)){
  temp_data2 <- read.csv(file_list2[i])
  temp_data2$`Research Areas` <- gsub(".csv","",file_list2[i])
  cncitenew <- rbind(cncitenew, temp_data2)
}
file_list2<-gsub(".csv","",file_list2)
cncite<-rbind(cncite,cncitenew)
cncite<-subset(cncite,as.numeric(cncite$PY) %in% c(2011:2020))

## US data for 31 disciplines 2011-20 ("US1120" dataset)
file_list3<-list.files()
uscite <- data.frame()
for (i in 1:length(file_list3)){
  temp_data3 <- read.delim(file_list3[i])
  temp_data3$`Research Areas` <- gsub(".txt","",file_list3[i])
  uscite <- rbind(uscite, temp_data3)
}
file_list3<-gsub(".csv","",file_list3)
uscite<-subset(uscite,as.numeric(uscite$PY) %in% c(2011:2020))

## Merge RP with Chinese data
cncite<-merge(cncite,rpp,by=c("Research Areas"),all.x=TRUE)

## Field/year variable:
cncite$fieldyear<-paste(cncite$`Research Areas`,cncite$PY)
## Variable for publication age:
cncite$age<-2023-as.numeric(cncite$PY)
## Treatment variable:
cncite$t2<-ifelse(as.numeric(cncite$PY)>2014,1,0)
## Log citation counts:
cncite$cites<-log(cncite$TC+1)
## Log RP:
cncite$rp<-log(cncite$rp)

## Two knowledge-intensity dummies based on RP:
## 1 if > = median RP, 0 otherwise:
cncite$rpdum1<-as.numeric(ifelse(cncite$rp < median(cncite$rp,na.rm=TRUE), 0, 1))
## 1 if RP > 1SD above mean, 0 if < 1SD below mean:
cncite$rpdum2<-as.numeric(ifelse(cncite$rp < (mean(cncite$rp,na.rm=TRUE)-sd(cncite$rp,na.rm=TRUE)), 0, ifelse(cncite$rp > (mean(cncite$rp,na.rm=TRUE)+sd(cncite$rp,na.rm=TRUE)),1,"NA")))

## Variable for number of authors:
cncite$auno<-str_count(cncite$AU,";")+1
## Remove obs without citation counts:
citeall<-cncite[!is.na(cncite$TC),]

## Subset data with >50% citations by field/year
cite50<-setDT(citeall)[,.SD[quantile(TC, 0.5)<
TC] , by = fieldyear]

## Summary statistics by discipline (numbers, citations, age, author count) # replicates Table A6 
citeall %>% dplyr:::count(`Research Areas`)
tapply(citeall$TC, citeall$`Research Areas`, summary)
tapply(citeall$age,citeall$`Research Areas`,summary)
tapply(citeall$auno,citeall$`Research Areas`,summary)

## Main negative binomial results # replicates Table 1
nbrp1<-fenegbin(TC~t2*rp + age + auno | SO, citeall) ## Journal FE
nbrp2<-fenegbin(TC~t2*rp + age + auno | SO, cite50) ## > 50% cited
## NB with two RP dummies:
nbrpdum1<-fenegbin(TC~t2*rpdum1 + age +auno | SO, citeall)
nbrpdum2<-fenegbin(TC~t2*rpdum2 + age +auno | SO, citeall)
## Results with discipline-clustered SEs:
etable(nbrp1, nbrp2, nbrpdum1, nbrpdum2, cluster = ~`Research Areas`, tex = TRUE)
## Incidence-rate ratios:
nbrp1.ir<-cbind(Estimate = coef(nbrp1), confint(nbrp1)[1:5,])
nbrp2.ir<-cbind(Estimate = coef(nbrp2), confint(nbrp2)[1:5,])
nbrpdum1.ir<-cbind(Estimate = coef(nbrpdum1), confint(nbrpdum1)[1:5,])
nbrpdum2.ir<-cbind(Estimate = coef(nbrpdum2), confint(nbrpdum2)[1:5,])
exp(nbrp1.ir)
exp(nbrp2.ir)
exp(nbrpdum1.ir)
exp(nbrpdum2.ir)

## Poisson robustness # replicates Table A10
poi1<-fepois(TC~t2*rp + age + auno | SO, citeall) ## Journal FE
poi2<-fepois(TC~t2*rp + age + auno | SO, cite50) ## > 50% cited
poidum1<-fepois(TC~t2*rpdum1 + age +auno | SO, citeall)
poidum2<-fepois(TC~t2*rpdum2 + age +auno | SO, citeall)
etable(poi1, poi2, poidum1, poidum2, cluster = ~`Research Areas`, tex = TRUE)
poi1.ir<-cbind(Estimate = coef(poi1), confint(poi1)[1:5,])
poi2.ir<-cbind(Estimate = coef(poi2), confint(poi2)[1:5,])
poidum1.ir<-cbind(Estimate = coef(poidum1), confint(poidum1)[1:5,])
poidum2.ir<-cbind(Estimate = coef(poidum2), confint(poidum2)[1:5,])
exp(poi1.ir)
exp(poi2.ir)
exp(poidum1.ir)
exp(poidum2.ir)

## Parallel trend plot # replicates Fig A6
## KI vs. non-KI using first dummy:
k1<-subset(citeall,citeall$rpdum1=="1")
nk1<-subset(citeall,citeall$rpdum1=="0")
## Total citation counts by year:
k1agg<-aggregate(k1$TC,by=list(k1$PY),FUN=sum)
nk1agg<-aggregate(nk1$TC,by=list(nk1$PY),FUN=sum)
## Log citation counts:
k1agg$lgcite<-log(k1agg$x)
nk1agg$lgcite<-log(nk1agg$x)
## Line plots with treatment:
plot(nk1agg$Group.1,nk1agg$lgcite,type="l",col="blue",lwd=2,ylim=c(12,14),xlab="Publication year",cex.lab=1.5,ylab="Logged total citations",main="")
lines(k1agg$Group.1,k1agg$lgcite,col="red",lwd=2)
abline(v = 2014.5,lty=2,lwd=2)
text(2015.2,12.6,substitute(paste(bold("2014 shock"))))
legend("bottomleft",legend=c("Knowledge-intensive","Non-knowledge-intensive"),col=c("red","blue"),pch=15)

## Parallel trend test
## Pre-treatment data:
citeallpt<-subset(citeall,as.numeric(citeall$PY)<2015)
## OLS with interaction of treatment uptake & time trend:
rpdum1trend<-feols(log(TC+0.1)~as.numeric(PY)*rpdum1 +age +auno | SO, citeallpt)
etable(rpdum1trend, cluster=~`Research Areas`, tex = TRUE) # replicates Table A9

## US-China DiD analysis
## Remove obs without citation counts for US data:
usall<-uscite[!is.na(uscite$TC),]
## Treatment & control variables:
usall$age<-2023-as.numeric(usall$PY)
usall$t2<-ifelse(as.numeric(usall$PY)>2014,1,0)
usall$auno<-str_count(usall$AU,";")+1
## Combine two datasets with China dummy:
usall$china<-0
citeall$china<-1
citeall$PY<-as.numeric(citeall$PY)
uscn<-bind_rows(usall,citeall)

## US-China DiD analysis # replicates Table 2
nbdd<-fenegbin(TC~t2*china + age + auno | `Research Areas` + SO, uscn)
poidd<-fepois(TC~t2*china + age + auno | `Research Areas` + SO, uscn)
etable(nbdd,poidd,cluster = ~`Research Areas`, tex = TRUE)
nbdd.ir<-cbind(Estimate = coef(nbdd), confint(nbdd)[1:5,])
poidd.ir<-cbind(Estimate = coef(poidd), confint(poidd)[1:5,])
exp(nbdd.ir)
exp(poidd.ir)