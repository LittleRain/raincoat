var W=D.W,WL=D.WL,PC=['#4f8fff','#34d399','#fbbf24','#a78bfa','#f472b6','#22d3ee','#f87171','#6366f1','#fb923c','#14b8a6'];
var L=W.length-1,P=Math.max(0,W.length-2);
// Register datalabels plugin
if(typeof ChartDataLabels!=='undefined')Chart.register(ChartDataLabels);
var DL={display:true,color:'#8b95ab',font:{size:9},anchor:'end',align:'top',formatter:function(v){return v>=1e6?(v/1e4).toFixed(0)+'万':v>=1000?Math.round(v).toLocaleString():v}};
var DLoff={display:false};
function F(v,t){if(t==='g')return'\u00a5'+(v>=1e6?(v/1e4).toFixed(1)+'\u4e07':v>=1000?Math.round(v).toLocaleString():v.toFixed(0));if(t==='p')return v>=1e8?(v/1e8).toFixed(2)+'\u4ebf':v>=1e4?(v/1e4).toFixed(1)+'\u4e07':v.toLocaleString();if(t==='%')return v.toFixed(2)+'%';if(t==='n')return v>=1e4?(v/1e4).toFixed(1)+'\u4e07':v.toLocaleString();return String(v)}
function G(c,l){if(!l||l===0)return{v:'-',c:''};var p=(c-l)/l*100;return{v:(p>0?'+':'')+p.toFixed(1)+'%',c:p>0?'up':'dn'}}
var _si={};
function sw(i){var b=document.querySelectorAll('.nav button'),s=document.querySelectorAll('.sec');for(var j=0;j<b.length;j++){b[j].className=j===i?'on':'';s[j].className=j===i?'sec on':'sec'}if(!_si[i]){_si[i]=true;setTimeout(function(){initSec(i)},50)}}
function mc(id,cfg){var e=document.getElementById(id);if(!e)return null;return new Chart(e,cfg)}
function V(l,v,c){var s='<div class="m"><div class="lb">'+l+'</div><div class="vl">'+v+'</div>';if(c)s+='<div class="ch '+c.c+'">'+c.v+'</div>';return s+'</div>'}
function T(c){if(!c||!c.c)return '<span class="tg">-</span>';return'<span class="tg tg-'+c.c+'">'+c.v+'</span>'}
function cw(v){return Math.min(Math.abs(v),9999).toFixed(1)}

function bS1(){
var x=D.s1.xd,z=D.s1.zy,r=D.s1.r;
var h='<div class="sec"><div class="stit">1. \u6838\u5fc3\u6570\u636e\u8d8b\u52bf</div><div class="sdesc">\u770b\u6e05\u5c0f\u5e97\u548c\u81ea\u8425GMV\u89c4\u6a21\u53d8\u5316</div>';
h+='<div class="g2"><div class="cd"><div class="cd-t">\ud83c\udfea \u5c0f\u5e97</div><div class="mr">';
h+=V('GMV',F(x[L].GMV,'g'),G(x[L].GMV,x[P].GMV));
h+=V('\u63a7\u6bd4',r[L]+'%',G(r[L],r[P]));
h+='</div><div class="mr">';
h+=V('\u4e70\u5bb6\u6570',F(x[L].b,'n'),G(x[L].b,x[P].b));
h+=V('\u8ba2\u5355\u6570',F(x[L].o,'n'),G(x[L].o,x[P].o));
h+=V('\u8f6c\u5316\u7387',F(x[L].cv,'%'));h+=V('GPM',''+x[L].GPM);
h+='</div></div><div class="cd"><div class="cd-t">\ud83c\udfe2 \u81ea\u8425</div><div class="mr">';
h+=V('GMV',F(z[L].GMV,'g'),G(z[L].GMV,z[P].GMV));
h+='</div><div class="mr">';
h+=V('\u4e70\u5bb6\u6570',F(z[L].b,'n'),G(z[L].b,z[P].b));
h+=V('\u8ba2\u5355\u6570',F(z[L].o,'n'),G(z[L].o,z[P].o));
h+=V('\u8f6c\u5316\u7387',F(z[L].cv,'%'));h+=V('GPM',''+z[L].GPM);
h+='</div></div></div>';
h+='<div class="g2"><div class="cd"><div class="cd-t">GMV\u8d8b\u52bf</div><div class="cc"><canvas id="c1a"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u63a7\u6bd4\u8d8b\u52bf</div><div class="cc"><canvas id="c1b"></canvas></div></div></div>';
h+='<div class="g2"><div class="cd"><div class="cd-t">\u4e70\u5bb6\u6570</div><div class="cc"><canvas id="c1c"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u8ba2\u5355\u6570</div><div class="cc"><canvas id="c1d"></canvas></div></div></div>';
h+='<div class="cbox"><h4>\ud83d\udcca \u7ed3\u8bba</h4><ul>';
var xWoW=x[P].GMV?((x[L].GMV-x[P].GMV)/x[P].GMV*100):0,zWoW=z[P].GMV?((z[L].GMV-z[P].GMV)/z[P].GMV*100):0;
var xTrend=xWoW>5?'\u73af\u6bd4\u4e0a\u6da8':(xWoW<-5?'\u73af\u6bd4\u4e0b\u6ed1':'\u57fa\u672c\u6301\u5e73');
var zTrend=zWoW>5?'\u73af\u6bd4\u4e0a\u6da8':(zWoW<-5?'\u73af\u6bd4\u4e0b\u6ed1':'\u57fa\u672c\u6301\u5e73');
var ppDiff=(r[L]-r[P]).toFixed(1);var ppSign=ppDiff>0?'+':'';
h+='<li><span class="hl">GMV:</span> \u5c0f\u5e97'+F(x[L].GMV,'g')+'('+G(x[L].GMV,x[P].GMV).v+'), '+xTrend+'\uff1b\u81ea\u8425'+F(z[L].GMV,'g')+'('+G(z[L].GMV,z[P].GMV).v+'), '+zTrend+'\u3002\u63a7\u6bd4'+r[L]+'%(\u4e0a\u5468'+r[P]+'%, '+ppSign+ppDiff+'pp)</li>';
h+='<li><span class="hl">\u4e70\u5bb6:</span> \u5c0f\u5e97'+F(x[L].b,'n')+'('+G(x[L].b,x[P].b).v+')\uff0c\u81ea\u8425'+F(z[L].b,'n')+'('+G(z[L].b,z[P].b).v+')</li>';
h+='<li><span class="hl">\u8ba2\u5355:</span> \u5c0f\u5e97'+F(x[L].o,'n')+'('+G(x[L].o,x[P].o).v+')\uff0c\u81ea\u8425'+F(z[L].o,'n')+'('+G(z[L].o,z[P].o).v+')</li>';
h+='<li><span class="hl">\u8f6c\u5316\u7387:</span> \u5c0f\u5e97'+F(x[L].cv,'%')+'(\u4e0a\u5468'+F(x[P].cv,'%')+')\uff0c\u81ea\u8425'+F(z[L].cv,'%')+'(\u4e0a\u5468'+F(z[P].cv,'%')+')</li>';
h+='</ul></div></div>';return h;}

function mkT(d,k,ti){
var h='<div class="cd"><div class="cd-t">'+ti+'</div><div class="ov"><table><tr><th>\u884c\u4e1a</th>';
var i;for(i=0;i<W.length;i++)h+='<th>'+W[i]+' GMV</th>';h+='<th>WoW</th>';
for(i=0;i<W.length;i++)h+='<th>'+W[i]+' \u4e70\u5bb6</th>';h+='<th>WoW</th>';
for(i=0;i<W.length;i++)h+='<th>'+W[i]+' \u8ba2\u5355</th>';h+='<th>WoW</th>';
for(i=0;i<W.length;i++)h+='<th>'+W[i]+' GPM</th>';h+='<th>GPM WoW</th></tr>';
for(var ki=0;ki<k.length;ki++){var n=k[ki],v=d[n];if(!v)continue;
var sub=n.indexOf('  ')===0;h+='<tr'+(sub?' class="sub-cat"':'')+'><td>'+n.trim()+'</td>';
for(i=0;i<W.length;i++)h+='<td>'+F(v[i].GMV,'g')+'</td>';h+='<td>'+T(G(v[L].GMV,v[P].GMV))+'</td>';
for(i=0;i<W.length;i++)h+='<td>'+F(v[i].b,'n')+'</td>';h+='<td>'+T(G(v[L].b,v[P].b))+'</td>';
for(i=0;i<W.length;i++)h+='<td>'+F(v[i].o,'n')+'</td>';h+='<td>'+T(G(v[L].o,v[P].o))+'</td>';
for(i=0;i<W.length;i++)h+='<td>'+v[i].GPM+'</td>';h+='<td>'+T(G(v[L].GPM,v[P].GPM))+'</td></tr>';}
return h+'</table></div></div>';}

function bS2(){var k=D.s2.k,a=D.s2.a,tp=D.tp||{};
var h='<div class="sec"><div class="stit">2. \u884c\u4e1a\u62c6\u89e3</div><div class="sdesc">\u6ce8\uff1a\u6574\u4f53\u6570\u636e\u65e0\u5546\u5bb6ID\uff0c\u201c\u975eACG-\u52a0\u6797\u201d\u5728\u6574\u4f53\u8868\u5f52\u5165\u201c\u5176\u4ed6\u201d\uff0c\u5728\u5546\u5bb6\u62c6\u89e3\u4e2d\u5355\u72ec\u5c55\u793a</div>';
h+='<div class="g2"><div class="cd"><div class="cd-t">\u6574\u4f53\u5206\u884c\u4e1aGMV\u8d8b\u52bf</div><div class="cc"><canvas id="c2a"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u884c\u4e1aGPM</div><div class="cc"><canvas id="c2b"></canvas></div></div></div>';
h+='<div class="cd"><div class="cd-t">\u5c0f\u5e97\u5206\u884c\u4e1a GMV\u8d8b\u52bf</div><div class="cc"><canvas id="c2c"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u5c0f\u5e97\u5206\u884c\u4e1a\u4e70\u5bb6\u8d8b\u52bf</div><div class="cc"><canvas id="c2d"></canvas></div></div>';
h+=mkT(a,k,'\u6570\u636e\u88681: \u6574\u4f53(\u81ea\u8425+\u5c0f\u5e97)');
h+=mkT(D.s2.x,k,'\u6570\u636e\u88682: \u5c0f\u5e97');h+=mkT(D.s2.y,k,'\u6570\u636e\u88683: \u81ea\u8425');
var _0={GMV:0,b:0,o:0,GPM:0},_e=W.map(function(){return _0});
var wf=a['\u975eACG-\u609f\u996d']||_e,zb=a['  \u73e0\u5b9d\u6587\u73a9']||_e,zz=a['  \u7ec4\u88c5\u673a']||_e;
var al=a['ACG-Allen']||_e,rz=a['  \u8f6f\u5468']||_e,mh=a['  \u76f2\u76d2']||_e;
var jl=a['\u975eACG-\u52a0\u6797']||_e;
var nz=a['ACG-\u5357\u5f81']||_e,yz=a['  \u786c\u5468']||_e,yx=a['  \u6e38\u620f\u865a\u62df']||_e,cb=a['  \u51fa\u7248\u7269']||_e;
// S2 归因: 商家维度拆解
function _s2reason(m){if(Math.abs(m.pw)>10&&Math.abs(m.gw)>10)return m.pw>0?'\u6d41\u91cf\u62c9\u5347(PV'+(m.pw>0?'+':'')+Math.min(Math.abs(m.pw),9999).toFixed(1)+'%)\u9a71\u52a8':'\u6d41\u91cf\u4e0b\u6ed1(PV'+Math.min(Math.abs(m.pw),9999).toFixed(1)+'%)\u5bfc\u81f4';if(m.cc!==m.cl&&Math.abs(((m.cc-m.cl)/(m.cl||1))*100)>10)return m.cc>m.cl?'\u8f6c\u5316\u7387\u63d0\u5347('+m.cl+'%\u2192'+m.cc+'%)\u9a71\u52a8':'\u8f6c\u5316\u7387\u4e0b\u964d('+m.cl+'%\u2192'+m.cc+'%)\u5bfc\u81f4';return '\u6d41\u91cf(PV'+(m.pw>0?'+':'')+Math.min(Math.abs(m.pw),9999).toFixed(1)+'%)+\u8f6c\u5316('+m.cl+'%\u2192'+m.cc+'%)\u7efc\u5408\u5f71\u54cd';}
var dt=D.s2.dt||{};
h+='<div class="cbox"><h4>\ud83d\udcca \u5c0f\u5e97\u884c\u4e1a\u5f52\u56e0</h4><ul>';
var xdt=dt.xd||{};
for(var dkey in xdt){if(!xdt.hasOwnProperty(dkey))continue;var dd=xdt[dkey];
h+='<li><span class="hl">\u5c0f\u5e97 '+dkey+':</span> GMV '+F(dd.gc,'g')+'('+G(dd.gc,dd.gl).v+'), \u6ce2\u52a8'+(dd.wow>0?'+':'')+dd.wow.toFixed(1)+'%\u3002';
var dms=dd.ms||[];for(var di=0;di<dms.length;di++){var dm=dms[di];h+=' \u2022 '+dm.s+' GMV '+F(dm.gc,'g')+'('+(dm.gw>900?'NEW':(dm.gw>0?'+':'')+dm.gw+'%')+'), '+_s2reason(dm)+'\u3002';}
h+='</li>';}
if(!Object.keys(xdt).length)h+='<li>\u5c0f\u5e97\u5404\u884c\u4e1a\u672c\u5468\u6ce2\u52a8\u5747\u572810%\u4ee5\u5185\uff0c\u6574\u4f53\u5e73\u7a33\u3002</li>';
h+='</ul></div>';
h+='<div class="cbox"><h4>\ud83d\udcca \u81ea\u8425\u884c\u4e1a\u5f52\u56e0</h4><ul>';
var ydt=dt.zy||{};
for(var dkey2 in ydt){if(!ydt.hasOwnProperty(dkey2))continue;var dd2=ydt[dkey2];
h+='<li><span class="hl">\u81ea\u8425 '+dkey2+':</span> GMV '+F(dd2.gc,'g')+'('+G(dd2.gc,dd2.gl).v+'), \u6ce2\u52a8'+(dd2.wow>0?'+':'')+dd2.wow.toFixed(1)+'%\u3002';
var dms2=dd2.ms||[];for(var di2=0;di2<dms2.length;di2++){var dm2=dms2[di2];h+=' \u2022 '+dm2.s+' GMV '+F(dm2.gc,'g')+'('+(dm2.gw>900?'NEW':(dm2.gw>0?'+':'')+dm2.gw+'%')+'), '+_s2reason(dm2)+'\u3002';}
h+='</li>';}
if(!Object.keys(ydt).length)h+='<li>\u81ea\u8425\u5404\u884c\u4e1a\u672c\u5468\u6ce2\u52a8\u5747\u572810%\u4ee5\u5185\uff0c\u6574\u4f53\u5e73\u7a33\u3002</li>';
h+='</ul></div></div>';
return h;}

function bS3(){var t=D.s3.t20;
var h='<div class="sec"><div class="stit">3. \u5c0f\u5e97\u5546\u5bb6\u62c6\u89e3</div><div class="sdesc">\u5c0f\u5e97\u5546\u5bb6\u4ea4\u6613\u89c4\u6a21\u53d8\u5316\uff0c\u5f52\u56e0\u6d41\u91cf\u4e0e\u8f6c\u5316</div>';
h+='<div class="cd"><div class="cd-t">Top10 GMV\u5468\u8d8b\u52bf</div><div class="cc"><canvas id="c3a"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u672c\u5468Top20(\u542bWoW)</div><div class="ov"><table>';
h+='<tr><th>#</th><th>\u5e97\u94fa</th><th>\u884c\u4e1a</th><th>\u7c7b\u76ee</th><th>\u672c\u5468GMV</th><th>\u4e0a\u5468GMV</th><th>GMV WoW</th><th>\u8d21\u732e\u7387</th><th>\u4e70\u5bb6</th><th>\u8ba2\u5355</th><th>\u5ba2\u5355\u4ef7</th><th>\u8f6c\u5316\u7387</th><th>GPM</th><th>PV</th><th>PV WoW</th></tr>';
for(var i=0;i<t.length;i++){var m=t[i];
var gw=m.gw>900?'NEW':(m.gw>0?'+':'')+m.gw+'%',gwc=m.gw>=0?'up':'dn';
var pw=m.pw>900?'NEW':(m.pw>0?'+':'')+m.pw+'%',pwc=m.pw>=0?'up':'dn';
h+='<tr><td>'+(i+1)+'</td><td>'+m.s+'</td><td>'+m.ind+'</td><td>'+m.cat+'</td>';
h+='<td>'+F(m.g,'g')+'</td><td>'+F(m.gl,'g')+'</td><td><span class="tg tg-'+gwc+'">'+gw+'</span></td>';
var ct=m.ctr||0;h+='<td>'+(ct>0?'+':'')+ct.toFixed(1)+'%</td>';
h+='<td>'+F(m.b,'n')+'</td><td>'+F(m.o,'n')+'</td><td>\u00a5'+Math.round(m.u)+'</td><td>'+m.cv+'%</td><td>'+m.gpm+'</td>';
h+='<td>'+F(m.pv,'p')+'</td><td><span class="tg tg-'+pwc+'">'+pw+'</span></td></tr>';}
h+='</table></div></div>';
var bc=D.s3.bc||{};for(var cat in bc){if(!bc.hasOwnProperty(cat))continue;var items=bc[cat];
h+='<div class="cd"><div class="cd-t">'+cat+' Top10</div><div class="ov"><table>';
h+='<tr><th>#</th><th>\u5e97\u94fa</th><th>GMV</th><th>WoW</th><th>\u8d21\u732e\u7387</th><th>\u4e70\u5bb6</th><th>\u8ba2\u5355</th><th>\u5ba2\u5355\u4ef7</th><th>\u8f6c\u5316\u7387</th><th>GPM</th></tr>';
for(var i=0;i<items.length;i++){var m=items[i];var gw2=m.gw>900?'NEW':(m.gw>0?'+':'')+m.gw+'%',gwc2=m.gw>=0?'up':'dn';
var ct2=m.ctr||0;
h+='<tr><td>'+(i+1)+'</td><td>'+m.s+'</td><td>'+F(m.g,'g')+'</td><td><span class="tg tg-'+gwc2+'">'+gw2+'</span></td><td>'+(ct2>0?'+':'')+ct2.toFixed(1)+'%</td><td>'+F(m.b,'n')+'</td><td>'+F(m.o,'n')+'</td><td>\u00a5'+Math.round(m.u)+'</td><td>'+m.cv+'%</td><td>'+m.gpm+'</td></tr>';}
h+='</table></div></div>';}
// S3 归因: 按行业拆解商家波动原因
var ia=D.s3.ia||{};
function _s3reason(m){var r='';var pvAbs=Math.min(Math.abs(m.pw),9999);var cvDelta=m.cc-m.cl;var cvPct=m.cl?Math.abs(cvDelta/m.cl*100):0;
if(pvAbs>10&&cvPct>10){r=m.pw>0?'\u6d41\u91cf\u62c9\u5347(PV+'+ pvAbs.toFixed(1)+'%)':'\u6d41\u91cf\u4e0b\u6ed1(PV-'+pvAbs.toFixed(1)+'%)';r+=cvDelta>0?'+\u8f6c\u5316\u7387\u63d0\u5347('+m.cl+'%\u2192'+m.cc+'%)':'+\u8f6c\u5316\u7387\u4e0b\u964d('+m.cl+'%\u2192'+m.cc+'%)';r+='\u53cc\u91cd\u9a71\u52a8';}
else if(pvAbs>10){r=m.pw>0?'\u6d41\u91cf\u62c9\u5347(PV+'+pvAbs.toFixed(1)+'%)\u4e3a\u4e3b\u8981\u9a71\u52a8\u56e0\u7d20':'\u6d41\u91cf\u4e0b\u6ed1(PV-'+pvAbs.toFixed(1)+'%)\u4e3a\u4e3b\u8981\u62d6\u7d2f\u56e0\u7d20';if(Math.abs(cvDelta)>0.1)r+=', \u8f6c\u5316\u7387'+m.cl+'%\u2192'+m.cc+'%';}
else if(cvPct>10){r=cvDelta>0?'\u8f6c\u5316\u7387\u63d0\u5347('+m.cl+'%\u2192'+m.cc+'%)\u4e3a\u4e3b\u8981\u9a71\u52a8\u56e0\u7d20':'\u8f6c\u5316\u7387\u4e0b\u964d('+m.cl+'%\u2192'+m.cc+'%)\u4e3a\u4e3b\u8981\u62d6\u7d2f\u56e0\u7d20';if(pvAbs>1)r+=', PV'+(m.pw>0?'+':'-')+pvAbs.toFixed(1)+'%';}
else{r='\u6d41\u91cf(PV'+(m.pw>0?'+':'-')+pvAbs.toFixed(1)+'%)+\u8f6c\u5316('+m.cl+'%\u2192'+m.cc+'%)\u7efc\u5408\u5f71\u54cd';}
return r;}
for(var iaKey in ia){if(!ia.hasOwnProperty(iaKey))continue;var iad=ia[iaKey];
h+='<div class="cbox"><h4>\ud83d\udcca '+iaKey+' \u5546\u5bb6\u5f52\u56e0 (GMV '+(iad.wow>0?'+':'')+iad.wow.toFixed(1)+'%)</h4><ul>';
var iams=iad.ms||[];
for(var iai=0;iai<iams.length;iai++){var iam=iams[iai];
h+='<li><span class="hl">'+iam.s+':</span> GMV '+F(iam.gc,'g')+'('+(iam.gw>900?'NEW':(iam.gw>0?'+':'')+iam.gw+'%')+'), \u8d21\u732e\u7387'+(iam.ctr>0?'+':'')+iam.ctr.toFixed(1)+'%\u3002<br/>\u2514 \u539f\u56e0: '+_s3reason(iam);
if(iam.pr&&iam.pr.length>0){h+='<br/>\u2514 \u6838\u5fc3\u5546\u54c1: ';for(var pi=0;pi<iam.pr.length;pi++){var pp=iam.pr[pi];if(pi>0)h+='; ';if(typeof pp==='string'){h+='\u300c'+pp+'\u300d';}else{h+='\u300c'+pp.n+'\u300d GMV '+F(pp.g,'g')+'\u3001\u5360\u5546\u5bb6'+pp.sh+'%';if(pp.cv>0)h+='\u3001\u8f6c\u5316\u7387'+pp.cv+'%';if(pp.gpm>0)h+='\u3001GPM '+pp.gpm;}}}
h+='</li>';}
h+='</ul></div>';}
if(!Object.keys(ia).length){h+='<div class="cbox"><h4>\ud83d\udcca \u5546\u5bb6\u6ce2\u52a8\u5206\u6790</h4><ul><li>\u672c\u5468\u5404\u884c\u4e1a\u5546\u5bb6\u6ce2\u52a8\u8f83\u5c0f\uff0c\u65e0\u663e\u8457\u5f02\u5e38\u3002</li></ul></div>';}
h+='</div>';
return h;}

function bS4(){var s=D.s4,tm=s.tm,fd=s.fd;
var h='<div class="sec"><div class="stit">4. \u6d41\u91cf\u6e20\u9053</div><div class="sdesc">\u6d41\u91cf\u5468\u7ef4\u5ea6\u53d8\u5316\u53ca\u8f6c\u5316\u6548\u7387</div>';
h+='<div class="g2"><div class="cd"><div class="cd-t">\u603b\u6d41\u91cf</div><div class="cc"><canvas id="c4a"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u5c0f\u5e97PV\u5360\u6bd4</div><div class="cc"><canvas id="c4b"></canvas></div></div></div>';
h+='<div class="cd"><div class="cd-t">\u6d41\u91cf\u603b\u89c8</div><div class="ov"><table>';
h+='<tr><th></th><th>PV</th><th>PV WoW</th><th>\u5360\u6bd4</th><th>CTR</th><th>\u8ba2\u5355</th><th>GMV</th><th>GMV WoW</th><th>GPM</th><th>\u5546\u8be6\u8f6c\u5316</th></tr>';
var lb=['\u6574\u4f53','\u5c0f\u5e97','\u81ea\u8425'],ds=[s.t,s.x,s.y],L4=W.length-1,P4=W.length-2;
var rt=['100%',s.xr[L4]+'%',(100-s.xr[L4]).toFixed(1)+'%'];
for(var i=0;i<3;i++){var d=ds[i];h+='<tr><td>'+lb[i]+'</td><td>'+F(d[L4].PV,'p')+'</td><td>'+T(G(d[L4].PV,d[P4].PV))+'</td><td>'+rt[i]+'</td><td>'+d[L4].CTR+'%</td><td>'+F(d[L4].o,'n')+'</td><td>'+F(d[L4].GMV,'g')+'</td><td>'+T(G(d[L4].GMV,d[P4].GMV))+'</td><td>'+d[L4].GPM+'</td><td>'+d[L4].scv+'%</td></tr>';}
h+='</table></div></div>';
function spT(data,nm){var t='<div class="cd"><div class="cd-t">'+nm+'</div><div class="ov"><table>';
t+='<tr><th>\u5468</th><th>\u6574\u4f53PV</th><th>PV WoW</th><th>\u6e20\u9053\u5360\u6bd4</th><th>\u5c0f\u5e97PV</th><th>\u5c0f\u5e97\u5360\u6bd4</th><th>\u6574\u4f53\u8ba2\u5355</th><th>\u5c0f\u5e97\u8ba2\u5355</th><th>\u6574\u4f53GMV</th><th>\u5c0f\u5e97GMV</th><th>\u5c0f\u5e97GMV\u5360\u6bd4</th><th>\u6574\u4f53GPM</th><th>\u5c0f\u5e97GPM</th><th>\u6574\u4f53CTR</th><th>\u5c0f\u5e97CTR</th><th>\u6574\u4f53\u8f6c\u5316</th><th>\u5c0f\u5e97\u8f6c\u5316</th></tr>';
for(var i=0;i<data.length;i++){var d=data[i];
var pw=i>0?T(G(d.PV,data[i-1].PV)):'-';var ow=i>0?T(G(d.o,data[i-1].o)):'-';var gw=i>0?T(G(d.GMV,data[i-1].GMV)):'-';
t+='<tr><td>'+WL[i]+'</td><td>'+F(d.PV,'p')+'</td><td>'+pw+'</td><td>'+d.rp+'%</td><td>'+F(d.xpv||0,'p')+'</td><td>'+d.xp+'%</td>';
t+='<td>'+F(d.o,'n')+'</td><td>'+(d.xo||0)+'</td><td>'+F(d.GMV,'g')+'</td><td>'+F(d.xGMV||0,'g')+'</td><td>'+(d.xGMVr||0)+'%</td>';
t+='<td>'+d.GPM+'</td><td>'+(d.xGPM||0)+'</td><td>'+d.CTR+'%</td><td>'+(d.xCTR||0)+'%</td><td>'+d.scv+'%</td><td>'+(d.xscv||0)+'%</td></tr>';}
return t+'</table></div></div>';}
h+=spT(tm,'\u5929\u9a6c\u63a8\u8350\u5546\u54c1\u5361');
h+='<div class="cd"><div class="cd-t">\u5929\u9a6c\u8d8b\u52bf</div><div class="cc"><canvas id="c4c"></canvas></div></div>';
h+=spT(fd,'\u5546\u57ce\u9996\u9875feed');
h+='<div class="cd"><div class="cd-t">Feed\u8d8b\u52bf</div><div class="cc"><canvas id="c4d"></canvas></div></div>';
function chT(data,ti){var t='<div class="cd"><div class="cd-t">'+ti+'</div><div class="ov"><table><tr><th>\u6e20\u9053</th>';
var wn=W.length;
for(var i=0;i<wn;i++)t+='<th>'+W[i]+' PV</th>';t+='<th>WoW</th><th>\u5360\u6bd4</th>';for(var i=0;i<wn;i++)t+='<th>'+W[i]+' GMV</th>';t+='<th>WoW</th>';for(var i=0;i<wn;i++)t+='<th>'+W[i]+' GPM</th>';t+='<th>GPM WoW</th></tr>';
for(var ch in data){if(!data.hasOwnProperty(ch))continue;var v=data[ch];t+='<tr><td>'+ch+'</td>';
for(var i=0;i<v.length;i++)t+='<td>'+(v[i]?F(v[i].PV,'p'):'-')+'</td>';var lw=wn-1,pw2=wn-2;var pc=(v[lw]&&v[pw2])?G(v[lw].PV,v[pw2].PV):{v:'-',c:''};t+='<td>'+T(pc)+'</td><td>'+(v[lw]&&v[lw].share?v[lw].share+'%':'-')+'</td>';
for(var i=0;i<v.length;i++)t+='<td>'+(v[i]?F(v[i].GMV,'g'):'-')+'</td>';var gc=(v[lw]&&v[pw2])?G(v[lw].GMV,v[pw2].GMV):{v:'-',c:''};t+='<td>'+T(gc)+'</td>';
for(var i=0;i<v.length;i++)t+='<td>'+(v[i]?v[i].GPM:'-')+'</td>';var gpc=(v[lw]&&v[pw2])?G(v[lw].GPM,v[pw2].GPM):{v:'-',c:''};t+='<td>'+T(gpc)+'</td></tr>';}return t+'</table></div></div>';}
h+=chT(s.cx,'\u5c0f\u5e97\u5206\u6e20\u9053');h+=chT(s.cy,'\u81ea\u8425\u5206\u6e20\u9053');
// 数据表3: 小店分行业×渠道
var s4i=s.ind||{};
for(var ind2 in s4i){if(!s4i.hasOwnProperty(ind2))continue;
h+='<div class="cd"><div class="cd-t">\u5c0f\u5e97 '+ind2+' \u5206\u6e20\u9053</div><div class="ov"><table><tr><th>\u6e20\u9053</th>';
var wn2=W.length;for(var i=0;i<wn2;i++)h+='<th>'+W[i]+' PV</th>';h+='<th>WoW</th>';for(var i=0;i<wn2;i++)h+='<th>'+W[i]+' GMV</th>';h+='<th>WoW</th></tr>';
var id2=s4i[ind2];for(var ch2 in id2){if(!id2.hasOwnProperty(ch2))continue;var v2=id2[ch2];
h+='<tr><td>'+ch2+'</td>';for(var i=0;i<v2.length;i++)h+='<td>'+(v2[i]?F(v2[i].PV,'p'):'-')+'</td>';
var lw2=wn2-1,pw3=wn2-2;var pc2=(v2[lw2]&&v2[pw3])?G(v2[lw2].PV,v2[pw3].PV):{v:'-',c:''};h+='<td>'+T(pc2)+'</td>';
for(var i=0;i<v2.length;i++)h+='<td>'+(v2[i]?F(v2[i].GMV,'g'):'-')+'</td>';
var gc2=(v2[lw2]&&v2[pw3])?G(v2[lw2].GMV,v2[pw3].GMV):{v:'-',c:''};h+='<td>'+T(gc2)+'</td></tr>';}
h+='</table></div></div>';}
// S4 小店流量归因: 渠道→经营类目拆解
var L=W.length-1,P=W.length-2;
h+='<div class="cbox"><h4>'+'\ud83d\udcca \u5c0f\u5e97\u6d41\u91cf\u603b\u89c8'+'</h4><ul>';
var xPvW=G(s.x[L].PV,s.x[P].PV),xGmvW=G(s.x[L].GMV,s.x[P].GMV);
h+='<li><span class="hl">\u5c0f\u5e97\u603b\u6d41\u91cf:</span> PV '+F(s.x[L].PV,'p')+'('+xPvW.v+'), GMV '+F(s.x[L].GMV,'g')+'('+xGmvW.v+'), \u5360\u6bd4'+s.xr[L]+'%(\u4e0a\u5468'+s.xr[P]+'%)</li>';
// 天马/Feed总览
h+='<li><span class="hl">\u5929\u9a6c(\u5c0f\u5e97):</span> PV '+F(tm[L].xpv||0,'p')+', \u5360\u6bd4'+tm[L].xp+'%(\u4e0a\u5468'+tm[P].xp+'%), GPM '+(tm[L].xGPM||0)+', \u8f6c\u5316'+(tm[L].xscv||0)+'%</li>';
h+='<li><span class="hl">Feed(\u5c0f\u5e97):</span> PV '+F(fd[L].xpv||0,'p')+', \u5360\u6bd4'+fd[L].xp+'%(\u4e0a\u5468'+fd[P].xp+'%), GPM '+(fd[L].xGPM||0)+', \u8f6c\u5316'+(fd[L].xscv||0)+'%</li>';
h+='</ul></div>';
// 渠道波动归因
var ca=s.ca||{};
var caKeys=Object.keys(ca);
if(caKeys.length>0){
h+='<div class="cbox"><h4>\ud83d\udcca \u5c0f\u5e97\u6e20\u9053\u6ce2\u52a8\u5f52\u56e0</h4><ul>';
for(var cai=0;cai<caKeys.length;cai++){var chName=caKeys[cai];var chD=ca[chName];
h+='<li><span class="hl">'+chName+':</span> PV '+F(chD.pv,'p')+'(PV'+(chD.pv_wow>0?'+':'')+chD.pv_wow.toFixed(1)+'%), GMV '+F(chD.gmv,'g')+'(GMV'+(chD.gmv_wow>0?'+':'')+chD.gmv_wow.toFixed(1)+'%)';
var cats=chD.cats||[];if(cats.length>0){h+='<br/>\u2514 \u7ecf\u8425\u7c7b\u76ee\u62c6\u89e3: ';
for(var cci=0;cci<cats.length;cci++){var cc=cats[cci];if(cci>0)h+='; ';
var ccReason='';
if(Math.abs(cc.pw)>10&&Math.abs(cc.gw)>10){ccReason=cc.pw>0?'\u6d41\u91cf+\u6210\u4ea4\u53cc\u6da8':'\u6d41\u91cf+\u6210\u4ea4\u53cc\u8dcc';}
else if(Math.abs(cc.pw)>10){ccReason=cc.pw>0?'\u6d41\u91cf\u62c9\u5347\u9a71\u52a8':'\u6d41\u91cf\u4e0b\u6ed1\u5bfc\u81f4';}
else if(cc.cc!==cc.cl&&Math.abs(((cc.cc-cc.cl)/(cc.cl||1))*100)>10){ccReason=cc.cc>cc.cl?'\u8f6c\u5316\u7387\u63d0\u5347\u9a71\u52a8':'\u8f6c\u5316\u7387\u4e0b\u964d\u5bfc\u81f4';}
else{ccReason='\u6d41\u91cf+\u8f6c\u5316\u7efc\u5408\u5f71\u54cd';}
h+=cc.n+'(GMV'+(cc.gw>0?'+':'')+(cc.gw>900?'NEW':cc.gw+'%')+', PV'+(cc.pw>0?'+':'')+(cc.pw>900?'NEW':cc.pw+'%')+', '+ccReason+')';}}
h+='</li>';}
h+='</ul></div>';}
h+='</div>';return h;}

function bS5(){var s=D.s5,ts=['\u5546\u54c1','\u89c6\u9891','\u52a8\u6001','\u76f4\u64ad','\u5176\u4ed6'],ik=s.ik||[];
var h='<div class="sec"><div class="stit">5. \u6210\u4ea4\u4f53\u88c1</div><div class="sdesc">\u4e0d\u540c\u4f53\u88c1\u4e0b\u7684\u6210\u4ea4\u89c4\u6a21\u53d8\u5316</div>';
h+='<div class="g3"><div class="cd"><div class="cd-t">\u6574\u4f53</div><div class="pie-c"><canvas id="c5a"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u5c0f\u5e97</div><div class="pie-c"><canvas id="c5b"></canvas></div></div>';
h+='<div class="cd"><div class="cd-t">\u81ea\u8425</div><div class="pie-c"><canvas id="c5c"></canvas></div></div></div>';
h+='<div class="cd"><div class="cd-t">\u4f53\u88c1\u5bf9\u6bd4(\u542bWoW)</div><div class="ov"><table>';
h+='<tr><th>\u4f53\u88c1</th><th>\u6574\u4f53GMV</th><th>\u5360\u6bd4</th><th>\u4e0a\u5468</th><th>\u53d8\u5316</th><th>GMV WoW</th><th>\u5c0f\u5e97GMV</th><th>\u5c0f\u5e97\u5360\u6bd4</th><th>\u5c0f\u5e97WoW</th><th>\u81ea\u8425GMV</th><th>\u81ea\u8425\u5360\u6bd4</th><th>\u81ea\u8425WoW</th></tr>';
for(var i=0;i<ts.length;i++){var t=ts[i];
var L5=W.length-1,P5=W.length-2;
var pp=(s.a[L5][t].p-s.a[P5][t].p).toFixed(2);var ppc=parseFloat(pp)>=0?'up':'dn';
h+='<tr><td>'+t+'</td><td>'+F(s.a[L5][t].g,'g')+'</td><td>'+s.a[L5][t].p+'%</td><td>'+s.a[P5][t].p+'%</td>';
h+='<td><span class="tg tg-'+ppc+'">'+(parseFloat(pp)>0?'+':'')+pp+'pp</span></td>';
h+='<td>'+T(G(s.a[L5][t].g,s.a[P5][t].g))+'</td>';
h+='<td>'+F(s.x[L5][t].g,'g')+'</td><td>'+s.x[L5][t].p+'%</td><td>'+T(G(s.x[L5][t].g,s.x[P5][t].g))+'</td>';
h+='<td>'+F(s.y[L5][t].g,'g')+'</td><td>'+s.y[L5][t].p+'%</td><td>'+T(G(s.y[L5][t].g,s.y[P5][t].g))+'</td></tr>';}
h+='</table></div></div>';
h+='<div class="stit">\u5c0f\u5e97\u5206\u884c\u4e1a</div>';
var ind=s.ind||{};
var L5=W.length-1,P5=W.length-2;
for(var idx=0;idx<ik.length;idx++){var cat=ik[idx];var data=ind[cat];if(!data)continue;
var cid='c5p'+idx;
h+='<div class="cd"><div class="cd-t">'+cat+'</div><div class="g2">';
h+='<div class="pie-c"><canvas id="'+cid+'"></canvas></div>';
h+='<div class="ov"><table><tr><th>\u4f53\u88c1</th><th>\u672c\u5468GMV</th><th>\u5360\u6bd4</th><th>\u4e0a\u5468GMV</th><th>\u4e0a\u5468\u5360\u6bd4</th><th>GMV WoW</th></tr>';
for(var ti=0;ti<ts.length;ti++){var t=ts[ti];
h+='<tr><td>'+t+'</td><td>'+F(data[L5][t].g,'g')+'</td><td>'+data[L5][t].p+'%</td>';
h+='<td>'+F(data[P5][t].g,'g')+'</td><td>'+data[P5][t].p+'%</td>';
h+='<td>'+T(G(data[L5][t].g,data[P5][t].g))+'</td></tr>';}
h+='</table></div></div></div>';}
// S5 conclusion - 小店视角
var lx=G(s.x[L5]['\u76f4\u64ad'].g,s.x[P5]['\u76f4\u64ad'].g);
h+='<div class="cbox"><h4>\ud83d\udcca \u5c0f\u5e97\u4f53\u88c1\u8bca\u65ad</h4><ul>';
// 找小店占比变化最大的体裁
var maxT='',maxTV=0,minT='',minTV=0;
for(var ti=0;ti<ts.length;ti++){var t=ts[ti];var d2=s.x[L5][t].p-s.x[P5][t].p;if(d2>maxTV){maxTV=d2;maxT=t;}if(d2<minTV){minTV=d2;minT=t;}}
// 总结
var xTotalGmv=0,xTotalGmvP=0;for(var ti=0;ti<ts.length;ti++){xTotalGmv+=s.x[L5][ts[ti]].g;xTotalGmvP+=s.x[P5][ts[ti]].g;}
var xTotalW=G(xTotalGmv,xTotalGmvP);
h+='<li><span class="hl">\u5c0f\u5e97\u6210\u4ea4\u603b\u89c8:</span> GMV '+F(xTotalGmv,'g')+'('+xTotalW.v+')\u3002';
// 涨最多的
if(maxT)h+=' \u2705 \u300c'+maxT+'\u300d\u5360\u6bd4\u63d0\u5347\u6700\u5927(+'+(maxTV).toFixed(2)+'pp\u81f3'+s.x[L5][maxT].p+'%), GMV '+F(s.x[L5][maxT].g,'g')+'('+G(s.x[L5][maxT].g,s.x[P5][maxT].g).v+')\u3002';
// 跌最多的
if(minT&&minTV<-0.1)h+=' \u26a0\ufe0f \u300c'+minT+'\u300d\u5360\u6bd4\u4e0b\u6ed1('+minTV.toFixed(2)+'pp\u81f3'+s.x[L5][minT].p+'%), GMV '+F(s.x[L5][minT].g,'g')+'('+G(s.x[L5][minT].g,s.x[P5][minT].g).v+')\u3002';
h+='</li>';
// 直播
h+='<li><span class="hl">\u5c0f\u5e97\u76f4\u64ad:</span> \u5360\u6bd4'+s.x[L5]['\u76f4\u64ad'].p+'%(\u4e0a\u5468'+s.x[P5]['\u76f4\u64ad'].p+'%), GMV '+F(s.x[L5]['\u76f4\u64ad'].g,'g')+'('+lx.v+')\u3002';
if(s.x[L5]['\u76f4\u64ad'].p>s.x[P5]['\u76f4\u64ad'].p)h+=' \u2705 \u76f4\u64ad\u5e26\u8d27\u80fd\u529b\u589e\u5f3a\uff0c\u5efa\u8bae\u52a0\u5927\u76f4\u64ad\u573a\u6b21\u548c\u5546\u5bb6\u6fc0\u52b1\u3002';
else h+=' \u26a0\ufe0f \u76f4\u64ad\u5360\u6bd4\u4e0b\u6ed1\uff0c\u9700\u68c0\u67e5\u5934\u90e8\u76f4\u64ad\u5546\u5bb6\u662f\u5426\u51cf\u5c11\u5f00\u64ad\u3002';
// 归因到行业
if(ind['\u975eACG-\u609f\u996d-\u73e0\u5b9d\u6587\u73a9']){var zb=ind['\u975eACG-\u609f\u996d-\u73e0\u5b9d\u6587\u73a9'];h+=' \u73e0\u5b9d\u6587\u73a9\u76f4\u64ad\u5360'+zb[L5]['\u76f4\u64ad'].p+'%('+G(zb[L5]['\u76f4\u64ad'].g,zb[P5]['\u76f4\u64ad'].g).v+')\uff1b';}
if(ind['ACG-Allen-\u8f6f\u5468']){var rz=ind['ACG-Allen-\u8f6f\u5468'];h+='\u8f6f\u5468\u76f4\u64ad\u5360'+rz[L5]['\u76f4\u64ad'].p+'%('+G(rz[L5]['\u76f4\u64ad'].g,rz[P5]['\u76f4\u64ad'].g).v+')';}
h+='</li>';
// 视频
var vw=G(s.x[L5]['\u89c6\u9891'].g,s.x[P5]['\u89c6\u9891'].g);
h+='<li><span class="hl">\u5c0f\u5e97\u89c6\u9891:</span> GMV '+F(s.x[L5]['\u89c6\u9891'].g,'g')+'('+vw.v+'), \u5360\u6bd4'+s.x[L5]['\u89c6\u9891'].p+'%\u3002';
if(s.x[L5]['\u89c6\u9891'].g>s.x[P5]['\u89c6\u9891'].g)h+=' \u2705 \u89c6\u9891\u5e26\u8d27\u589e\u957f\u3002';
else h+=' \u26a0\ufe0f \u89c6\u9891\u6210\u4ea4\u4e0b\u6ed1\uff0c\u9700\u5173\u6ce8\u5185\u5bb9\u8d28\u91cf\u548c\u6295\u653e\u7b56\u7565\u3002';
if(ind['\u975eACG-\u609f\u996d-\u7ec4\u88c5\u673a']){var zzj=ind['\u975eACG-\u609f\u996d-\u7ec4\u88c5\u673a'];h+=' \u7ec4\u88c5\u673a\u89c6\u9891\u5360'+zzj[L5]['\u89c6\u9891'].p+'%('+G(zzj[L5]['\u89c6\u9891'].g,zzj[P5]['\u89c6\u9891'].g).v+')\u3002';}
h+='</li>';
// 商品（基盘）
var spW=G(s.x[L5]['\u5546\u54c1'].g,s.x[P5]['\u5546\u54c1'].g);
h+='<li><span class="hl">\u5c0f\u5e97\u5546\u54c1(\u57fa\u76d8):</span> \u5360\u6bd4'+s.x[L5]['\u5546\u54c1'].p+'%(\u4e0a\u5468'+s.x[P5]['\u5546\u54c1'].p+'%), GMV '+F(s.x[L5]['\u5546\u54c1'].g,'g')+'('+spW.v+')\u3002';
if(s.x[L5]['\u5546\u54c1'].p<s.x[P5]['\u5546\u54c1'].p&&s.x[L5]['\u5546\u54c1'].g>s.x[P5]['\u5546\u54c1'].g)h+=' \u5546\u54c1\u4f53\u88c1GMV\u4ecd\u5728\u589e\u957f\uff0c\u5360\u6bd4\u4e0b\u964d\u662f\u56e0\u4e3a\u5185\u5bb9\u4f53\u88c1\u589e\u901f\u66f4\u5feb\uff0c\u8fd9\u662f\u5065\u5eb7\u7684\u5185\u5bb9\u7535\u5546\u7ed3\u6784\u8f6c\u578b\u3002';
h+='</li>';
h+='</ul></div></div>';return h;}

/* ===== LAZY CHART INIT ===== */
function initSec(i){
Chart.defaults.color='#8b95ab';Chart.defaults.borderColor='rgba(31,43,71,.4)';Chart.defaults.font.family="'Noto Sans SC',system-ui";
if(i===0){
var x=D.s1.xd,z=D.s1.zy;
mc('c1a',{type:'bar',data:{labels:WL,datasets:[{label:'\u5c0f\u5e97',data:x.map(function(d){return d.GMV}),backgroundColor:'rgba(79,143,255,.7)',borderRadius:4},{label:'\u81ea\u8425',data:z.map(function(d){return d.GMV}),backgroundColor:'rgba(167,139,250,.7)',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:function(v){return F(v,'g')}}}}}});
mc('c1b',{type:'line',data:{labels:WL,datasets:[{label:'\u63a7\u6bd4%',data:D.s1.r,borderColor:'#fbbf24',backgroundColor:'rgba(251,191,36,.1)',fill:true,tension:.3,pointRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:function(v){return v+'%'}}}}}});
mc('c1c',{type:'line',data:{labels:WL,datasets:[{label:'\u5c0f\u5e97',data:x.map(function(d){return d.b}),borderColor:'#4f8fff',tension:.3},{label:'\u81ea\u8425',data:z.map(function(d){return d.b}),borderColor:'#a78bfa',tension:.3}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:function(v){return F(v,'n')}}}}}});
mc('c1d',{type:'bar',data:{labels:WL,datasets:[{label:'\u5c0f\u5e97',data:x.map(function(d){return d.o}),backgroundColor:'rgba(79,143,255,.7)',borderRadius:4},{label:'\u81ea\u8425',data:z.map(function(d){return d.o}),backgroundColor:'rgba(167,139,250,.7)',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{ticks:{callback:function(v){return F(v,'n')}}}}}});
}
if(i===1){
var ik=['ACG-\u5357\u5f81','ACG-Allen','\u975eACG-\u609f\u996d','\u975eACG-\u52a0\u6797','\u5176\u4ed6'];
mc('c2a',{type:'line',data:{labels:WL,datasets:ik.filter(function(k){return D.s2.a[k]}).map(function(k,i){return{label:k,data:D.s2.a[k].map(function(d){return d.GMV}),borderColor:PC[i],tension:.3,borderWidth:2}})},options:{responsive:true,maintainAspectRatio:false,plugins:{datalabels:DLoff},scales:{y:{ticks:{callback:function(v){return F(v,'g')}}}}}});
mc('c2b',{type:'line',data:{labels:WL,datasets:ik.filter(function(k){return D.s2.a[k]}).map(function(k,i){return{label:k,data:D.s2.a[k].map(function(d){return d.GPM}),borderColor:PC[i],tension:.3}})},options:{responsive:true,maintainAspectRatio:false}});
// 小店分行业GMV趋势
mc('c2c',{type:'line',data:{labels:WL,datasets:ik.filter(function(k){return D.s2.x[k]}).map(function(k,i){return{label:k,data:D.s2.x[k].map(function(d){return d.GMV}),borderColor:PC[i],tension:.3,borderWidth:2}})},options:{responsive:true,maintainAspectRatio:false,plugins:{datalabels:DLoff},scales:{y:{ticks:{callback:function(v){return F(v,'g')}}}}}});
// 小店分行业买家趋势
mc('c2d',{type:'line',data:{labels:WL,datasets:ik.filter(function(k){return D.s2.x[k]}).map(function(k,i){return{label:k,data:D.s2.x[k].map(function(d){return d.b}),borderColor:PC[i],tension:.3,borderWidth:2}})},options:{responsive:true,maintainAspectRatio:false,plugins:{datalabels:DLoff},scales:{y:{ticks:{callback:function(v){return F(v,'n')}}}}}});
}
if(i===2){
var tr=D.s3.tr,tl=WL.slice(-3),ti2=0,tds=[];
var trNames=Object.keys(tr);
for(var n in tr){if(!tr.hasOwnProperty(n))continue;var showLbl=ti2<5;tds.push({label:n.length>8?n.substring(0,8)+'\u2026':n,data:tr[n],borderColor:PC[ti2%PC.length],tension:.3,borderWidth:showLbl?2.5:1.5,borderDash:showLbl?[]:[3,3],datalabels:{display:showLbl}});ti2++;}
mc('c3a',{type:'line',data:{labels:tl,datasets:tds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:9},usePointStyle:true}}},scales:{y:{ticks:{callback:function(v){return F(v,'g')}}}}}});
}
if(i===3){
mc('c4a',{type:'bar',data:{labels:WL,datasets:[{label:'\u5c0f\u5e97',data:D.s4.x.map(function(d){return d.PV}),backgroundColor:'rgba(79,143,255,.7)',borderRadius:4},{label:'\u81ea\u8425',data:D.s4.y.map(function(d){return d.PV}),backgroundColor:'rgba(167,139,250,.7)',borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true},y:{stacked:true,ticks:{callback:function(v){return F(v,'p')}}}}}});
mc('c4b',{type:'bar',data:{labels:WL,datasets:[{type:'bar',label:'\u5c0f\u5e97PV',data:D.s4.x.map(function(d){return d.PV}),backgroundColor:'rgba(79,143,255,.4)',borderRadius:4,yAxisID:'y'},{type:'line',label:'\u5360\u6bd4%',data:D.s4.xr,borderColor:'#34d399',backgroundColor:'rgba(52,211,153,.1)',tension:.3,pointRadius:4,yAxisID:'y1'}]},options:{responsive:true,maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:function(v){return F(v,'p')}}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+'%'}}}}}});
mc('c4c',{type:'bar',data:{labels:WL,datasets:[{type:'bar',label:'\u6574\u4f53PV',data:D.s4.tm.map(function(d){return d.PV}),backgroundColor:'rgba(139,149,171,.3)',borderRadius:4,yAxisID:'y'},{type:'bar',label:'\u5c0f\u5e97PV',data:D.s4.tm.map(function(d){return d.xpv||0}),backgroundColor:'rgba(79,143,255,.6)',borderRadius:4,yAxisID:'y'},{type:'bar',label:'\u81ea\u8425PV',data:D.s4.tm.map(function(d){return d.ypv||0}),backgroundColor:'rgba(167,139,250,.5)',borderRadius:4,yAxisID:'y'},{type:'line',label:'\u5c0f\u5e97%',data:D.s4.tm.map(function(d){return d.xp}),borderColor:'#fbbf24',tension:.3,yAxisID:'y1'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{datalabels:DLoff},scales:{y:{position:'left',ticks:{callback:function(v){return F(v,'p')}}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+'%'}}}}}});
mc('c4d',{type:'bar',data:{labels:WL,datasets:[{type:'bar',label:'\u6574\u4f53PV',data:D.s4.fd.map(function(d){return d.PV}),backgroundColor:'rgba(139,149,171,.3)',borderRadius:4,yAxisID:'y'},{type:'bar',label:'\u5c0f\u5e97PV',data:D.s4.fd.map(function(d){return d.xpv||0}),backgroundColor:'rgba(52,211,153,.6)',borderRadius:4,yAxisID:'y'},{type:'bar',label:'\u81ea\u8425PV',data:D.s4.fd.map(function(d){return d.ypv||0}),backgroundColor:'rgba(167,139,250,.5)',borderRadius:4,yAxisID:'y'},{type:'line',label:'\u5c0f\u5e97%',data:D.s4.fd.map(function(d){return d.xp}),borderColor:'#fbbf24',tension:.3,yAxisID:'y1'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{datalabels:DLoff},scales:{y:{position:'left',ticks:{callback:function(v){return F(v,'p')}}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+'%'}}}}}});
}
if(i===4){
var ts2=['\u5546\u54c1','\u89c6\u9891','\u52a8\u6001','\u76f4\u64ad','\u5176\u4ed6'];
function mkP(id,data,idx){mc(id,{type:'doughnut',data:{labels:ts2,datasets:[{data:ts2.map(function(t){return data[idx][t].p}),backgroundColor:PC.slice(0,5),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{padding:8,usePointStyle:true,font:{size:10}}}}}})}
mkP('c5a',D.s5.a,3);mkP('c5b',D.s5.x,3);mkP('c5c',D.s5.y,3);
var indK=D.s5.ik||[],indD=D.s5.ind||{};
for(var idx=0;idx<indK.length;idx++){
var cid='c5p'+idx;
if(document.getElementById(cid)&&indD[indK[idx]]){mkP(cid,indD[indK[idx]],3);}
}
}
}

document.getElementById('app').innerHTML=bS1()+bS2()+bS3()+bS4()+bS5();
document.querySelectorAll('.sec')[0].classList.add('on');
_si[0]=true;setTimeout(function(){initSec(0)},50);
