"""Synthetic warm-cache rendering benchmark; no external map requests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys, tempfile, statistics, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QPixmap, QColor
from src.route_editor import RouteMap
app=QApplication([])
points=[{'latitude':31.028 + i*0.0000003, 'longitude':121.444 + (i%100)*0.000001} for i in range(5000)]
with tempfile.TemporaryDirectory() as temp, patch('src.route_editor.get_config_path',return_value=str(Path(temp)/'config.json')), patch.object(RouteMap,'_load_tile'):
    widget=RouteMap(points)
    widget.resize(1050,600)
    widget.zoom=16
    widget.center=__import__('src.route_editor',fromlist=['project']).project(31.0285,121.4445,16)
    tile=QPixmap(256,256); tile.fill(QColor('#eef2f4'))
    x,y=int(widget.center.x()/256),int(widget.center.y()/256)
    for tx in range(x-8,x+9):
        for ty in range(y-8,y+9): widget._tiles[(16,tx,ty)]=tile
    widget.show(); app.processEvents()
    pix=QPixmap(widget.size())
    for _ in range(10): widget.render(pix)
    times=[]
    for i in range(180):
        widget.center+=QPointF(0.4,-0.2)
        start=time.perf_counter(); widget.render(pix); times.append((time.perf_counter()-start)*1000)
    result={'route_points':5000,'frames':len(times),'median_ms':round(statistics.median(times),3),'p95_ms':round(sorted(times)[int(len(times)*.95)],3),'max_ms':round(max(times),3),'mode':'offscreen warm-cache QWidget.render, 1050x600 logical pixels'}
    print(json.dumps(result))
    widget.close(); widget.deleteLater(); QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
