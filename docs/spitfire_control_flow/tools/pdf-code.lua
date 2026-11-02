-- Inline code is deliberately left to Pandoc's exact literal-string writer.
-- Long code blocks wrap without inserted hyphens; no device command is run.
function Header(el)
  local heading=pandoc.utils.stringify(el.content)
  -- These two dense table sections need the heading, column heads and first
  -- complete record together. The reserve fits that group at the shared scale.
  if el.level==2 and (heading:match('^5%.3 ') or heading=='Unknowns that remain open' or heading=='남아 있는 미확인 사항') then
    return {pandoc.RawBlock('latex','\\Needspace{14\\baselineskip}'),el}
  end
  return el
end
function Code(el)
  if #el.text>25 and el.text:match('^[-%w_/:.#?]+$') then
    return pandoc.RawInline('latex','\\nolinkurl{'..el.text..'}')
  end
  local escapes={['\\']='\\textbackslash{}',['&']='\\&',['%']='\\%',['$']='\\$',['#']='\\#',['_']='\\_',['{']='\\{',['}']='\\}',['~']='\\textasciitilde{}',['^']='\\textasciicircum{}',[' ']='\\ '}
  local out=''
  for c in el.text:gmatch('.') do
    out=out..(escapes[c] or c)
    if c:match('[/_:%.%- ]') then out=out..'\\allowbreak{}' end
  end
  return pandoc.RawInline('latex','\\texttt{'..out..'}')
end
function Div(el)
  for _,c in ipairs(el.classes) do
    if c=='landscape' then
      local out={pandoc.RawBlock('latex','\\begin{landscape}')}
      for _,block in ipairs(el.content) do table.insert(out,block) end
      table.insert(out,pandoc.RawBlock('latex','\\end{landscape}'))
      return out
    end
  end
  return el
end
function CodeBlock(el)
  return pandoc.RawBlock('latex', '\\begin{Verbatim}[breaklines=true,breakanywhere=true,fontsize=\\small]\n' .. el.text .. '\n\\end{Verbatim}')
end
