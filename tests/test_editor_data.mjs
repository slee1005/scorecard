import test from 'node:test';
import assert from 'node:assert/strict';
import {shotNumber, currentTheme, THEMES} from '../src/golf_video_studio/web/editor-data.js';

test('manual shot number survives reorder; blank restores auto',()=>{
  const a={id:'a',hole:1},b={id:'b',hole:1,number:7},c={id:'c',hole:2};
  assert.equal(shotNumber([a,b,c],b),7);
  assert.equal(shotNumber([b,a,c],b),7);
  assert.equal(shotNumber([a,b,c],c),1);
  b.number=null;assert.equal(shotNumber([a,b,c],b),2);
});
test('themes only replace colors and preserve user alpha/position',()=>{
  const style={...THEMES.broadcast,overlay_opacity:.45,opacity:.6,x:.2};
  Object.assign(style,THEMES.forest);
  assert.equal(currentTheme(style),'forest');
  assert.equal(style.overlay_opacity,.45);assert.equal(style.opacity,.6);assert.equal(style.x,.2);
  style.accent='#abcdef';assert.equal(currentTheme(style),'custom');
});
