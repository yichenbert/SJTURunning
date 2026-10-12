"""Offline integration check: real Qt WebEngine + WebChannel, mocked AMap SDK.

This verifies editor wiring, not provider authentication or real map accuracy.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from src.amap_view import AMapView, MapPage
MapPage.javaScriptConsoleMessage = lambda self, level, message, line, source: print("JS", message, line, flush=True)

app = QApplication([])
html = (Path(__file__).resolve().parents[2] / 'assets/amap.html').read_text()
stub = '''
window.AMap={
 Map:class{constructor(){this.events={};setTimeout(()=>this.events.complete?.(),30);}
 on(k,f){this.events[k]=f;}add(){}remove(){}setStatus(){}setDefaultCursor(){}setFitView(){}setZoomAndCenter(){}setZoom(){}getZoom(){return 16;}
 lngLatToContainer(p){let a=Array.isArray(p)?p:[p.lng,p.lat];return {getX:()=>a[0]*100000,getY:()=>a[1]*100000};}},
 Polyline:class{constructor(o){this.path=o.path;}setPath(p){this.path=p;}},
 Marker:class{constructor(o){this.options=o;this.events={};}on(k,f){this.events[k]=f;}}
};start();
'''
html = html.replace('document.head.appendChild(script);',stub)
with patch('src.amap_view.Path.read_text',return_value=html):
    view = AMapView(settings={'key':'offline-test','security_code':'offline-test'})
view.resize(900,600);view.show()
def wait_for(check):
    for _ in range(150):
        app.processEvents();QTest.qWait(20)
        if check():return
    raise AssertionError('WebChannel operation timed out')
wait_for(lambda:view.ready)
view.web.page().runJavaScript("map.events.click({lnglat:{lng:121.449,lat:31.027}});map.events.click({lnglat:{lng:121.450,lat:31.028}});")
wait_for(lambda:len(view.points)==2)
assert abs(view.points[0]['longitude']-121.449)>.003
assert len(view.history)==2
view.set_mode('freehand')
view.web.page().runJavaScript("map.events.mousedown({lnglat:{lng:121.451,lat:31.029},originEvent:{button:0}});map.events.mousemove({lnglat:{lng:121.452,lat:31.030}});map.events.mouseup();")
wait_for(lambda:len(view.points)==4)
assert len(view.history)==3
view.undo();assert len(view.points)==2
view.clear_route();assert view.points==[]
original=[{'latitude':31.0285,'longitude':121.4445},{'latitude':31.029,'longitude':121.448}]
view.set_route(original)
results=[]
view.flush_route(results.append)
wait_for(lambda:bool(results))
assert results==[True] and view.points==original
history_count=len(view.history)
view.web.page().runJavaScript("map.events.mousedown({lnglat:{lng:121.453,lat:31.031},originEvent:{button:0}});map.events.mousemove({lnglat:{lng:121.454,lat:31.032}});")
results=[]
view.flush_route(results.append)
wait_for(lambda:bool(results))
assert results==[True] and len(view.points)==4
assert view.points[:2]==original
assert len(view.history)==history_count+1
view.shutdown();view.close();view.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
print('PASS: real WebEngine/WebChannel bootstrap, click, freehand, WGS84 conversion, stroke undo, clear, unchanged vertices and last-stroke save flush; AMap SDK mocked offline')
