#!/usr/bin/env Rscript
# Primary chart renderer. No plot is produced if the verified extract is absent.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) stop('Usage: Rscript chart.R rows.csv chart.svg')
if (!requireNamespace('ggplot2', quietly = TRUE)) stop('ggplot2 is required')
plot_csv <- args[[1]]
plot_svg <- args[[2]]
if (!file.exists(plot_csv)) stop('No verified chart input')
d <- read.csv(plot_csv, colClasses=c('character','character','character','numeric'))
stopifnot(all(c('period','port_code','country_code','value_usd') %in% names(d)))
stopifnot(nrow(d)>0L, all(nchar(d$port_code)==4L), all(nchar(d$country_code)==4L),
          all(is.finite(d$value_usd[!is.na(d$value_usd)])), all(d$value_usd[!is.na(d$value_usd)]>=0))
library(ggplot2)

# Design contract used across every ggplot2 chart.
theme_lithographie <- function(base_size=11) {
  theme_minimal(base_family='sans', base_size=base_size) +
    theme(
      panel.grid.major.y=element_blank(),
      panel.grid.minor=element_blank(),
      panel.grid.major.x=element_line(colour='#E4E6EA',linewidth=.25),
      panel.border=element_blank(),
      plot.background=element_rect(fill='#FFFFFF',colour=NA),
      panel.background=element_rect(fill='#FFFFFF',colour=NA),
      strip.background=element_rect(fill='#F1F2F5',colour='#C7CDD6',linewidth=.25),
      strip.text=element_text(face='plain',colour='#141B28',size=9),
      axis.text=element_text(colour='#252B34',size=9),
      axis.title=element_text(colour='#636B75',size=9),
      plot.title=element_text(face='plain',colour='#141B28',size=14),
      plot.subtitle=element_text(colour='#626975',size=9),
      plot.caption=element_text(colour='#636B75',hjust=0,size=8),
      plot.title.position='plot',
      plot.caption.position='plot',
      legend.position='none',
      plot.margin=margin(18,16,14,12)
    )
}
if (all(d$port_code=='ALL') && all(d$country_code=='ALL')) {
  d$period <- factor(d$period, levels=sort(unique(d$period)))
  p <- ggplot(d, aes(x=period,y=value_usd/1e6,fill=period)) +
    geom_col(width=.44) +
    scale_fill_manual(values=c('#9BA0AA','#213CBA')) +
    scale_y_continuous(expand=expansion(mult=c(0,.08)),labels=function(x)format(round(x),big.mark=',')) +
    labs(title='U.S. imports · unwrought aluminum',
         subtitle='HS 760110 · January, matched years · monthly Census HS6 totals',
         x=NULL,y='Reported value · USD millions',
         caption='Census Port HS6 · sum of all matching origin and customs-port records · nominal USD') +
    theme_lithographie()
  ggsave(plot_svg,plot=p,width=10,height=5,device=grDevices::svg,units='in',bg='white')
} else {
# Show the largest port-country pairs in either period; missing records stay NA.
d$key <- paste0('PORT ',d$port_code,' · ORIGIN ',d$country_code)
maxes <- aggregate(value_usd ~ key,data=d,FUN=function(x)max(x,na.rm=TRUE))
maxes <- maxes[order(-maxes$value_usd,maxes$key),]
keys <- head(maxes$key,12L)
d <- d[d$key %in% keys & !is.na(d$value_usd),]
d$key <- factor(d$key,levels=rev(keys))
d$period <- factor(d$period, levels=sort(unique(d$period)))
p <- ggplot(d,aes(x=value_usd/1e6,y=key,fill=period)) +
  geom_col(width=.63,show.legend=FALSE) +
  facet_wrap(~period,nrow=1,scales='fixed') +
  scale_fill_manual(values=c('#9BA0AA','#213CBA')) +
  scale_x_continuous(expand=expansion(mult=c(0,.08)),labels=function(x)format(round(x,1),trim=TRUE,big.mark=',')) +
  labs(title='Imports by customs port and country of origin',
       subtitle='HS 760110 · matched January months · observed monthly value',
       x='USD millions',y=NULL,
       caption='Census Port HS6 · no bar means no reported record for that pair · nominal USD') +
  theme_lithographie()
# grDevices::svg is bundled with base R on ordinary macOS/Linux installations.
ggsave(plot_svg,plot=p,width=12,height=6.5,device=grDevices::svg,units='in',bg='white')

}
