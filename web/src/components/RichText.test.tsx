import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RichText } from './RichText';

describe('RichText', () => {
  it('turns the Markdown habits of AI answers into elements', () => {
    const html = renderToStaticMarkup(<RichText text={'Net Addr: **192.168.1.0**\n- mask `255.255.255.0`\n1. Giữ NetID'} />);
    expect(html).toContain('<strong>192.168.1.0</strong>');
    expect(html).toContain('<ul><li>mask <code>255.255.255.0</code></li></ul>');
    expect(html).toContain('<ol><li>Giữ NetID</li></ol>');
  });

  it('never treats answer text as HTML', () => {
    expect(renderToStaticMarkup(<RichText text="<b>x</b> `<i>`" />)).toContain('&lt;b&gt;x&lt;/b&gt; <code>&lt;i&gt;</code>');
  });
});
