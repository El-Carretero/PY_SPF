%% Documented derivative of XL-STD-DOC-001 Rev A for this review report.
%% This is not an official approved xLaPPLAs template or laboratory approval.
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{xlapplas-doc-review}[2026/11/02 standards-derived review class]
\LoadClass[10pt,a4paper,twoside]{article}
\RequirePackage[inner=22mm,outer=18mm,top=19mm,bottom=20mm,headheight=9pt,headsep=5mm,footskip=10mm]{geometry}
\RequirePackage{fontspec}
\setmainfont{URWGothic-Book.otf}[Path=/usr/share/fonts/opentype/urw-base35/,BoldFont=URWGothic-Demi.otf,ItalicFont=URWGothic-BookOblique.otf,BoldItalicFont=URWGothic-DemiOblique.otf]
\setsansfont{URWGothic-Book.otf}[Path=/usr/share/fonts/opentype/urw-base35/,BoldFont=URWGothic-Demi.otf,ItalicFont=URWGothic-BookOblique.otf,BoldItalicFont=URWGothic-DemiOblique.otf]
\setmonofont{DejaVu Sans Mono}[Scale=1.0]
\RequirePackage{unicode-math}
\setmathfont{Latin Modern Math}
\RequirePackage{xcolor}
\definecolor{XLgray80}{HTML}{333333}
\definecolor{XLgray60}{HTML}{666666}
\definecolor{XLgray35}{HTML}{A6A6A6}
\definecolor{XLgray15}{HTML}{D9D9D9}
\definecolor{XLgray05}{HTML}{F2F2F2}
\RequirePackage{graphicx,grffile,booktabs,longtable,array,calc}
\RequirePackage{ragged2e,titlesec,caption,fancyhdr,lastpage,pdflscape,needspace}
\RequirePackage{fvextra,seqsplit,xurl,etoolbox,enumitem}
\RequirePackage[unicode,hidelinks]{hyperref}
\RequirePackage{bookmark}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4.2mm}
\setlength{\emergencystretch}{2em}
\setlength{\tabcolsep}{4pt}
\setlength{\LTpre}{4.2mm}
\setlength{\LTpost}{4.2mm}
\setlength{\heavyrulewidth}{0.6pt}
\setlength{\lightrulewidth}{0.35pt}
\renewcommand{\arraystretch}{1.16}
\renewcommand{\normalsize}{\fontsize{9.2}{12.2}\selectfont}
\renewcommand{\small}{\fontsize{8.5}{11}\selectfont}
\renewcommand{\footnotesize}{\fontsize{8.2}{10.5}\selectfont}
\AtBeginDocument{\normalsize\RaggedRight}
\AtBeginEnvironment{longtable}{\footnotesize\RaggedRight}
\AtBeginEnvironment{tabular}{\RaggedRight}
\titleformat{\section}{\raggedright\hyphenpenalty=10000\fontsize{18}{22}\selectfont\bfseries}{\thesection}{0.7em}{}
\titleformat{\subsection}{\fontsize{11.5}{14}\selectfont\bfseries}{\thesubsection}{0.7em}{}
\titleformat{\subsubsection}{\fontsize{10.5}{13}\selectfont\bfseries}{\thesubsubsection}{0.7em}{}
\titlespacing*{\section}{0pt}{8.4mm}{4.2mm}
\titlespacing*{\subsection}{0pt}{8.4mm}{2.1mm}
\titlespacing*{\subsubsection}{0pt}{4.2mm}{2.1mm}
% Source documents carry explicit controlled decimal section numbers.
\setcounter{secnumdepth}{0}
\setcounter{tocdepth}{2}
\captionsetup{font=footnotesize,labelformat=empty,justification=raggedright,singlelinecheck=false,skip=4.2mm}
\setlist{leftmargin=5mm,itemsep=1.2mm,topsep=2.1mm,parsep=0pt}
\setlength{\headwidth}{\textwidth}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\fontsize{7}{8.5}\selectfont\textcolor{XLgray80}{\XLshorttitle}}
\fancyhead[R]{\fontsize{7}{8.5}\selectfont\textcolor{XLgray80}{\XLnumber\ | \XLrevision}}
\fancyfoot[L]{\fontsize{7}{8.5}\selectfont\textcolor{XLgray60}{\XLclassification\ | xlapplas.com}}
\fancyfoot[R]{\fontsize{7}{8.5}\selectfont\thepage\ / \pageref*{LastPage}}
\renewcommand{\headrulewidth}{0.35pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{\fancyhf{}\fancyfoot[L]{\fontsize{7}{8.5}\selectfont\XLclassification\ | xlapplas.com}\fancyfoot[R]{\fontsize{7}{8.5}\selectfont\thepage\ / \pageref*{LastPage}}\renewcommand{\headrulewidth}{0pt}}
\clubpenalty=10000
\widowpenalty=10000
\displaywidowpenalty=10000
\raggedbottom
\newcommand{\tightlist}{\setlength{\itemsep}{1.2mm}\setlength{\parskip}{0pt}}
\newcommand{\codeword}[1]{\texttt{\seqsplit{#1}}}
\newcommand{\passthrough}[1]{#1}
\newcommand{\pandocbounded}[1]{#1}
