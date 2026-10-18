import { createApp, nextTick } from 'vue';
import { afterEach, expect, it, vi } from 'vitest';
const apps=[];
afterEach(()=>{ apps.splice(0).forEach(app=>app.unmount()); document.body.innerHTML=''; });
async function mount(props={}) {
  const modules=import.meta.glob('../SafetyRejectedNotice.vue');
  expect(modules['../SafetyRejectedNotice.vue'], 'Safety rejection notice exists').toBeTypeOf('function');
  const View=(await modules['../SafetyRejectedNotice.vue']()).default;
  const emit=vi.fn();
  const el=document.createElement('div'); document.body.appendChild(el);
  const app=createApp(View,{reason:'Exits blocked',canMarkRevised:true,...props,onMarkRevised:emit});
  apps.push(app); app.mount(el); await nextTick(); return {el,emit};
}
it('renders the badge, reason and revision guidance and emits the action', async()=>{
  const {el,emit}=await mount();
  expect(el.querySelector('[data-testid=venue-safety-rejected]')).not.toBeNull();
  for(const text of ['Safety rejected','Exits blocked','Revise the arrangement with venue staff, then mark it revised and send the event for safety check again.']) expect(el.textContent).toContain(text);
  expect(el.querySelector('button').textContent).toContain('Mark as revised');
  el.querySelector('button').click(); expect(emit).toHaveBeenCalledOnce();
});
it('hides the action outside Planning',async()=>{const {el}=await mount({canMarkRevised:false}); expect(el.querySelector('button')).toBeNull();});
it('disables the action while busy',async()=>{const {el,emit}=await mount({busy:true}); expect(el.querySelector('button').disabled).toBe(true); el.querySelector('button').click(); expect(emit).not.toHaveBeenCalled();});
