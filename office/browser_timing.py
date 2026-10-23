"""Observed timings only. Never infer page/AI time from total elapsed time."""
import time


class BrowserTiming:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.started=clock();self.active={};self.totals={};self.count=0

    def observe(self,event,item):
        kind=item.get('type','');identifier=item.get('id')
        if not identifier:return
        if kind in ('mcpToolCall','mcp_tool_call'):
            name=str(item.get('server',''))+' '+str(item.get('tool',''))
            category='browser_tool' if any(x in name.lower() for x in ('browser','cua','ego')) else 'other_tool'
        elif kind in ('commandExecution','command_execution'):
            category='browser_tool' if 'ego-browser' in str(item.get('command','')).lower() else 'command_tool'
        elif kind=='reasoning':category='reasoning_item'
        else:return
        if event in ('item/started','item.started'):
            self.active.setdefault(identifier,(self.clock(),category))
        elif event in ('item/completed','item.completed'):
            old=self.active.pop(identifier,None)
            if category=='browser_tool':self.count+=1
            if old:
                start,category=old
                self.totals[category]=self.totals.get(category,0)+(self.clock()-start)*1000

    def summary(self):
        return {'total_ms':round((self.clock()-self.started)*1000,2),'browser_tool_calls':self.count,
                'observed_ms':{k:round(v,2) for k,v in self.totals.items()},'unfinished_items':len(self.active),
                'navigation_ms':None,'snapshot_ms':None,'click_input_ms':None,'site_wait_ms':None,'ai_inference_ms':None,
                'note':'도구 호출 왕복 관측값입니다. 배치 내부 동작·사이트 대기·AI 추론 시간은 제공되지 않으면 null입니다. 합산 시간은 병렬 호출에서 겹칠 수 있습니다.'}
