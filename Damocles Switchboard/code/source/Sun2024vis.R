######## Damocles' Switchboard: Information Externalities And the Autocratic Logic of Internet Control ########
######## Meicen Sun ########

###### Visualizations ######

require(heatmaply)
require(imputeTS)

#### Digital product substitutability visualization #### replicates Fig 1
## Search engine traffic data for Google & Baidu in China:
search<-read.csv("CNsearch.csv")
date<-as.yearmon(search$Date)
## Plot with disruptions overlaid:
par(mar=c(5.1, 4.5, 4.1, 2.1))
plot(date,search$Google,type="l",xlab="",ylab="Relative share (%)",cex.lab=2,lwd=3, col="blue",main="")
lines(date,search$Baidu,type="l",lwd=3,col="red")
axis(side=1,lwd=1,lwd.ticks=4,at=c(2009:2018),lend=1,labels=FALSE,tcl=-1)
abline(v=(2009+2/12),lwd=3,lty=2)
abline(v=(2009+5/12),lty=2)
abline(v=(2009+6/12),lwd=3,lty=2)
abline(v=(2009+9/12),lwd=3,lty=2)
abline(v=(2012+3/12),lty=2)
abline(v=(2012+10/12),lty=2)
abline(v=(2014),lty=2)
abline(v=(2014+5/12),lwd=3,lty=2)
abline(v=(2014+11/12),lwd=3,lty=2)
abline(v=(2010+2/12),lty=2)
text(2013.5, 15, cex=1.5,"Google")
text(2013.5, 82, cex=1.5, "Baidu")

#### Internet control visualization #### replicates Fig 3
## Interpolate Internet control data & transform for reverse chronological order:
gfw<-read.csv("gfwfinal.csv")
gfw<-gfw[,2:101]
m<-sapply(gfw,na_interpolation)
m<-t(m)
m<-apply(m,2,rev)
m<-t(m)
m<-apply(m,2,rev)
m<-t(m)
m<-apply(m,2,rev)
## Heatmap:
heatmaply(m, Rowv=FALSE, Colv=FALSE, colors = c("red","green"),showticklabels=c(FALSE,FALSE),row_dend_left=FALSE,hide_colorbar=TRUE)