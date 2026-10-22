// Contract smoke test for the vanilla Streamlit bridge; no model or browser account.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('office/component/index.html','utf8');
const script=html.match(/<script>([\s\S]*)<\/script>/)[1];
const nodes=new Map(),messages=[],handlers={};
function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',dataset:{},style:{},attributes:{},classList:{toggle(){},add(){},remove(){}},setAttribute(name,value){this.attributes[name]=value},querySelector(s){return node(key+s)},addEventListener(event,handler){(this.events??={})[event]??=[];this.events[event].push(handler)}});return nodes.get(key)}
const parent={postMessage(message){messages.push(message)}};
const context={document:{querySelector:node,querySelectorAll:()=>[],body:{scrollHeight:800}},window:{parent,addEventListener(type,handler){handlers[type]=handler}},performance:{now:()=>0},ResizeObserver:class{observe(){}},setTimeout,clearTimeout,requestAnimationFrame:()=>1,cancelAnimationFrame(){},Date,Math,console};
vm.runInNewContext(script,context);
assert(messages.some(m=>m.type==='streamlit:componentReady'&&m.apiVersion===1));
handlers.message({source:parent,data:{type:'streamlit:render',args:{selected:'dev',tasks:[{role:'dev',status:'running'}]}}});
assert.equal(node('#employee-task-state').textContent,'작업 중');
const listeners=node('#desks').events.click;
listeners.forEach(handler=>handler({target:{closest:()=>({dataset:{role:'plan'}})}}));
assert(messages.some(m=>m.type==='streamlit:setComponentValue'&&m.value.role==='plan'));
handlers.message({source:parent,data:{type:'streamlit:render',args:{attention_count:3,tasks:[]}}});
const badge=node('[data-role="ceo"].owner-alert');
assert.equal(badge.hidden,false);
assert.equal(badge.querySelector('.owner-count').textContent,'3');
assert(node('[data-role="ceo"]').attributes['aria-label'].includes('3건'));
listeners.forEach(handler=>handler({target:{closest:()=>({dataset:{role:'ceo'}})}}));
assert(messages.some(m=>m.type==='streamlit:setComponentValue'&&m.value.action==='open_inbox'&&m.value.role==='ceo'));
handlers.message({source:parent,data:{type:'streamlit:render',args:{attention_count:120,tasks:[]}}});
assert.equal(badge.querySelector('.owner-count').textContent,'99+');
handlers.message({source:parent,data:{type:'streamlit:render',args:{attention_count:0,tasks:[]}}});
assert.equal(badge.hidden,true);
console.log('Office component handshake, avatar selection and owner alert count/open/clear contracts passed');

handlers.message({source:parent,data:{type:'streamlit:render',args:{selected:'dev',tasks:[{role:'dev',status:'running',state:'researching',detail:'웹 검색 이벤트',stale:false}]}}});
assert.equal(node('[data-role="dev"]').querySelector('.bubble').textContent,'조사');
assert(node('#employee-task-state').textContent.includes('웹 검색 이벤트'));
handlers.message({source:parent,data:{type:'streamlit:render',args:{selected:'dev',tasks:[{role:'dev',status:'running',state:'researching',stale:true}]}}});
assert.equal(node('[data-role="dev"]').querySelector('.bubble').textContent,'응답 지연');
assert(node('#employee-task-state').textContent.includes('응답 지연'));
console.log('Observed activity and stale presence contracts passed');
