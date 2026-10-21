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
  for(const text of ['Safety rejected','Exits blocked','Revise the arrangement with venue staff and mark it revised, or replace the venue. Then send the event for safety check again.']) expect(el.textContent).toContain(text);
  expect(el.querySelector('button').textContent).toContain('Mark as revised');
  el.querySelector('button').click(); await nextTick();
  const dialog=el.querySelector('[role=dialog]');
  expect(dialog).not.toBeNull(); expect(emit).not.toHaveBeenCalled();
});
it('hides the action outside Planning',async()=>{const {el}=await mount({canMarkRevised:false}); expect(el.querySelector('button')).toBeNull();});
it('disables the action while busy',async()=>{const {el,emit}=await mount({busy:true}); expect(el.querySelector('button').disabled).toBe(true); el.querySelector('button').click(); expect(emit).not.toHaveBeenCalled();});

it('asks for a required note, counts it and emits it trimmed', async()=>{
  const {el,emit}=await mount(); el.querySelector('button').click(); await nextTick();
  const dialog=el.querySelector('[role=dialog]');
  expect(dialog.textContent).toContain('What changed, or what should the Safety Officer know?');
  const confirm=()=>[...dialog.querySelectorAll('button')].find(b=>b.textContent.includes('Mark as revised'));
  expect(confirm().disabled).toBe(true);
  const input=dialog.querySelector('textarea'); expect(input.maxLength).toBe(1000);
  input.value='   '; input.dispatchEvent(new Event('input')); await nextTick();
  expect(confirm().disabled).toBe(true);
  input.value='  Moved the barriers '; input.dispatchEvent(new Event('input')); await nextTick();
  expect(dialog.textContent).toContain(`${input.value.length} / 1000`);
  confirm().click(); expect(emit).toHaveBeenCalledWith('Moved the barriers');
});
it('emits replace',async()=>{
  const replace=vi.fn(); const {el}=await mount({canReplace:true,onReplace:replace});
  [...el.querySelectorAll('button')].find(b=>b.textContent.includes('Replace venue')).click();
  expect(replace).toHaveBeenCalledOnce();
});
it('names a requested replacement and hides both actions',async()=>{
  const {el}=await mount({canReplace:true,replacement:{venue_name:'Town Hall'}});
  expect(el.textContent).toContain('Replacement requested: Town Hall');
  expect(el.querySelector('button')).toBeNull();
});
it('cancels without sending a note',async()=>{
  const {el,emit}=await mount(); el.querySelector('button').click(); await nextTick();
  [...el.querySelectorAll('button')].find(b=>b.textContent==='Cancel').click(); await nextTick();
  expect(el.querySelector('[role=dialog]')).toBeNull(); expect(emit).not.toHaveBeenCalled();
});
