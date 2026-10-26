"""Portable checks for trusted child-directed browser qualification; no browser emulation claim."""

from pathlib import Path
import subprocess


def test_native_child_pointer_is_visible_fixed_and_does_not_write_camera():
    from scripts.architecture_explorer import story_render

    path = Path(story_render.__file__).with_name("story_capture.cjs")
    js = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
assert(source.includes("['center','left-gap','right-gap','child-focus']"));
assert(source.includes("route==='child-focus'&&!page.childPointer"));
assert(source.includes('nativeChildPointer:pages[1].childPointer'));
assert(source.includes("JSON.stringify(pages[0].childPointer)!==JSON.stringify(pages[1].childPointer)"));
assert(source.includes("['priority','dependencies']"));
assert(source.includes("r.node==='arbora'&&r.route==='center'"));
assert(source.includes("throw Error('No trusted mouse-wheel chart reveal on '"));
const expression=source.split("page.childPointer=await page.evaluate(`")[1].split('`);')[0].replace('${JSON.stringify(node)}','"parent"');
const cam=Object.freeze({x:0,y:0,k:1}),rects={nearest:[130,90,40,30],far:[10,20,30,30],clipped:[295,95,30,30],below:[130,310,40,30],viewportClipped:[130,255,40,30]};
const environment={PAYLOAD:{tree:{id:'parent',children:Object.keys(rects).map(id=>({id,children:[]}))}},__arch:{cam,rect:id=>rects[id]},document:{querySelector:()=>({getBoundingClientRect:()=>({x:10,y:20,width:300,height:300})})},innerWidth:320,innerHeight:300};
const before=JSON.stringify(environment.__arch.cam),result=vm.runInNewContext(expression,environment);
assert.equal(result.id,'nearest');assert.equal(result.x,160);assert.equal(result.y,125);assert.equal(JSON.stringify(environment.__arch.cam),before);
environment.PAYLOAD.tree.children=[{id:'clipped',children:[]},{id:'below',children:[]},{id:'viewportClipped',children:[]}];
assert.throws(()=>vm.runInNewContext(expression,environment),/No initially visible native child/);
"""
    subprocess.run(["node", "-e", js, str(path)], check=True, capture_output=True, text=True)
