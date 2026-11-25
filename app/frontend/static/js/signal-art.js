// Project a ribbed toroidal coil into the poster. Depth sorting hides the rear ribs.
const canvas=document.getElementById('signal-art');
function draw(){
 const w=canvas.clientWidth,h=canvas.clientHeight,d=Math.min(devicePixelRatio,2);
 canvas.width=w*d;canvas.height=h*d;const ctx=canvas.getContext('2d');ctx.scale(d,d);
 const rings=[],tau=2*Math.PI,k=Math.min(w*.28,h*.33);
 for(let i=0;i<136;i++){
  const t=tau*i/136,path=new Path2D();let depth=0;
  for(let j=0;j<=70;j++){
   const v=tau*j/70,r=1+.43*Math.cos(v),x=r*Math.cos(t),y=r*Math.sin(t),z=.43*Math.sin(v)+.22*Math.sin(2*t);
   const a=x*.86+z*.51,b=y*.68-(-x*.51+z*.86)*.735;
   const sx=(a*.89+b*.455)*k+w*.5,sy=(-a*.455+b*.89)*k+h*(w<=760?.72:.5);
   if(j===0)path.moveTo(sx,sy);else path.lineTo(sx,sy);
   depth+=(y*.735+(-x*.51+z*.86)*.68)/71;
  }
  rings.push({path,depth,t});
 }
 for(const ring of rings.sort((a,b)=>a.depth-b.depth)){
  const light=.5+.5*Math.cos(ring.t+1.2);
  ctx.fillStyle='#183c29';ctx.fill(ring.path);
  ctx.strokeStyle='hsl('+(76+light*8)+' 91% '+(41+light*35)+'%)';ctx.lineWidth=1.35;ctx.stroke(ring.path);
 }
}
new ResizeObserver(draw).observe(canvas);
