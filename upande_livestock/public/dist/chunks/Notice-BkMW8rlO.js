import{o as s,j as r,c as t}from"../livestock-Bf_2oYmQ.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const l=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"m9 12 2 2 4-4",key:"dzmm74"}]],o=s("CircleCheck",l);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const p=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 16v-4",key:"1dtifu"}],["path",{d:"M12 8h.01",key:"e9boi3"}]],m=s("Info",p);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=[["path",{d:"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",key:"wmoenq"}],["path",{d:"M12 9v4",key:"juzpu7"}],["path",{d:"M12 17h.01",key:"p32p05"}]],i=s("TriangleAlert",x),g=/<\/?(br|p|div|li|h[1-6])[^>]*>/gi,b=/<[^>]+>/g;function d(e){return typeof e!="string"||!e.includes("<")?e:e.replace(g,`
`).replace(b,"").replace(/&nbsp;/g," ").replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/\n{3,}/g,`

`).trim()}function v({tone:e,children:a,className:n}){const c=e==="error"?i:e==="ok"?o:m;return r.jsxs("div",{role:e==="error"?"alert":"status",className:t("flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] border px-3.5 py-3 text-[13px] leading-relaxed whitespace-pre-line",e==="error"&&"border-[rgba(196,48,43,0.24)] bg-[rgba(196,48,43,0.06)] text-[var(--sd-sev-critical)]",e==="ok"&&"border-[rgba(63,143,79,0.28)] bg-[rgba(63,143,79,0.07)] text-[var(--sd-sev-moderate)]",e==="info"&&"border-[var(--sd-line)] bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]",n),children:[r.jsx(c,{className:"mt-0.5 h-4 w-4 shrink-0"}),r.jsx("div",{className:"min-w-0 flex-1",children:d(a)})]})}function f({children:e}){return r.jsxs("div",{className:"flex items-start gap-2.5 rounded-[var(--sd-radius-lg)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-3.5 py-3 text-[13px] leading-relaxed text-[var(--sd-amber)]",children:[r.jsx(i,{className:"mt-0.5 h-4 w-4 shrink-0"}),r.jsx("div",{className:"min-w-0 flex-1",children:d(e)})]})}function h({children:e}){return r.jsx("span",{className:"inline-flex items-center gap-1 rounded-[var(--sd-radius-pill)] border border-[var(--sd-amber-line)] bg-[var(--sd-amber-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--sd-amber)]",children:e})}function k({tone:e,children:a}){return r.jsx("span",{className:t("inline-flex items-center rounded-[var(--sd-radius-pill)] px-2.5 py-1 text-[11px] font-medium",e==="ok"&&"bg-[rgba(63,143,79,0.10)] text-[var(--sd-sev-moderate)]",e==="short"&&"bg-[rgba(196,48,43,0.09)] text-[var(--sd-sev-critical)]",e==="mute"&&"bg-[var(--sd-bg-soft)] text-[var(--sd-muted)]"),children:a})}export{f as A,o as C,h as M,v as N,k as P,i as T};
