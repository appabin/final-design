#import "@preview/itemize:0.2.0" as el
#import "@preview/cuti:0.4.0": fakebold, show-cn-fakebold
#import "@preview/numbly:0.1.0": numbly
#import "@preview/algo:0.3.6": algo, code, comment, d, i

#let FONTSIZE = (
  三号: 16pt,
  小三: 15pt,
  四号: 14pt,
  小四: 12pt,
  五号: 10.5pt,
  小五: 9pt,
)

// Windows fonts from the original template are used first. In particular,
// Windows 宋体 is identified by Typst as "SimSun".
#let FontEnglish = (
  (name: "Times New Roman", covers: "latin-in-cjk"),
  (name: "STIX Two Text", covers: "latin-in-cjk"),
)

#let FontHeiCN = (
  "SimHei",
  "Microsoft YaHei",
  "Noto Sans CJK SC",
  "Heiti SC",
)
#let FontHei = (
  (name: "Times New Roman", covers: "latin-in-cjk"),
  (name: "STIX Two Text", covers: "latin-in-cjk"),
  "SimHei",
  "Microsoft YaHei",
  "Noto Sans CJK SC",
  "Heiti SC",
)
#let FontSongCN = "SimSun"
#let FontSong = (
  (name: "Times New Roman", covers: "latin-in-cjk"),
  (name: "STIX Two Text", covers: "latin-in-cjk"),
  "SimSun",
  "Noto Serif CJK SC",
  "Songti SC",
)
#let FontKai = (
  (name: "Times New Roman", covers: "latin-in-cjk"),
  (name: "STIX Two Text", covers: "latin-in-cjk"),
  "KaiTi",
  "FZKai-Z03",
  "FZKTK",
)

#let tableCounter = counter("Table")
#let figureCounter = counter("Figure")
#let equationCounter = counter("Equation")
#let algorithmCounter = counter("Algorithm")

#let BUPTBachelorThesis(
  titleZH: "",
  abstractZH: "",
  keywordsZH: (),
  titleEN: "",
  abstractEN: "",
  keywordsEN: (),
  equation-numbering-location: right + bottom,
  body,
) = {
  assert((right, right + bottom).contains(equation-numbering-location), message: "can be only right or right + bottom")
  // 页面配置
  set page(paper: "a4", margin: 2.5cm)
  set text(font: FontSong, weight: "regular", size: FONTSIZE.小四)

  show: el.paragraph-enum-list.with(
    indent: 0em,
    label-indent: 2em,
  ) // 有序列表与内容基线对齐，首行/悬挂缩进对齐word模板
  show: show-cn-fakebold // 中文伪粗体

  // 数学公式
  set math.equation(
    numbering: it => context if equation-numbering-location == right [
      // 改用numbering实现，可在正文 @label
      #let chapterLevel = counter(heading).at(here()).at(0)
      #set text(font: FontSong)
      #h(0em, weak: true)
      (#chapterLevel\-#equationCounter.display())
      #h(0em, weak: true)
      #equationCounter.step()
    ],
    supplement: none, // 取消自带的 supplement "Equation"
  )
  show math.equation.where(block: true): set block(
    above: 0em,
    below: 0em,
  )
  show math.equation.where(block: true): it => block(
    above: 1.5em,
    below: 1.5em,
    width: 100%,
    {
      it
      if equation-numbering-location == right + bottom {
        // 公式编号在下一行右侧
        align(right, {
          let chapterLevel = counter(heading).at(here()).at(0)
          set text(font: FontSong)
          [(#chapterLevel\-#equationCounter.display())]
          equationCounter.step()
        })
      }
    },
  )
  // @equation => 式4-1
  show ref: it => {
    let el = it.element
    if el != none and el.func() == math.equation {
      let loc = el.location()
      let chapter = counter(heading).at(loc).first()
      let eq-num = equationCounter.at(loc).first()
      link(loc)[式 #chapter\-#eq-num]
    } else if el != none and el.func() == heading {
      let numbers = counter(heading).at(el.location())
      h(0em, weak: true)
      link(el.location())[
        #numbering(el.numbering, ..numbers)
      ]
      if numbers.len() != 1 [节]
      h(0em, weak: true)
    } else {
      it
    }
  }

  // 代码
  show raw.where(block: true): it => {
    set block(stroke: 0.5pt, width: 100%, inset: 1em)
    it
  }

  // 中文摘要
  align(center)[
    #set text(font: FontHei, weight: "bold")
    #v(0.6cm)
    #text(size: FONTSIZE.三号, titleZH)
    #v(1.4cm)
    #text(size: FONTSIZE.小三, "摘要")
    #v(0.45cm)
  ]

  set par(
    first-line-indent: (all: true, amount: 2em), // 首行缩进
    leading: 1.2em, // 段内行间距为1.25倍，不等于 1.25em
    spacing: 1.2em, // 段间距同样为1.25倍，不等于 1.25em
    justify: true, // 两端对齐
  )
  abstractZH

  [\ \ ]
  text(
    font: FontHeiCN,
    weight: "bold",
    size: FONTSIZE.小四,
    h(2em) + "关键词" + h(0.5em),
  )
  text(size: FONTSIZE.小四, keywordsZH.join(h(1em)))
  pagebreak(weak: true)

  // 英文摘要
  align(center)[
    #v(0.2cm)
    #text(weight: "bold", size: FONTSIZE.三号, titleEN)
    #v(1.5cm)
    #text(weight: "bold", size: FONTSIZE.小三, "ABSTRACT")
    #v(0.8cm)
  ]

  [
    #set par(
      leading: 1.05em,
      spacing: 1.05em,
    )
    #abstractEN
  ]


  [\ ]
  text(weight: "bold", size: FONTSIZE.小四, h(2em) + "KEY WORDS")
  text(size: FONTSIZE.小四, for value in keywordsEN {
    h(1em) + value
  })

  pagebreak(weak: true)

  // 标题样式
  set heading(numbering: numbly(
    "第{1:一}章", // use {level:format} to specify the format
    "{1}.{2}", // if format is not specified, arabic numbers will be used
    "{1}.{2}.{3}",
    "{1}.{2}.{3}.{4}", // here, we only want the 4th level
  ))
  show heading: it => {
    if it.level == 1 {
      pagebreak(weak: true) // 大标题换页，不强制奇数页，避免生成空白偶数页
      tableCounter.update(1)
      figureCounter.update(1)
      equationCounter.update(1)
      algorithmCounter.update(1)
    }
    if it.level <= 4 {
      let idx = it.level - 1
      let size = (FONTSIZE.三号, FONTSIZE.四号, FONTSIZE.小四, FONTSIZE.五号).at(idx)
      let above = (0pt, 1.5em, 1.5em, 1.5em).at(idx)
      let below = (2.8em, 1.5em, 1.5em, 1.5em).at(idx)
      let indent = (0em, 0em, 2em, 2em).at(idx)
      let number = if it.numbering != none {
        numbering(it.numbering, ..counter(heading).at(it.location()))
        h(0.5em)
      }
      set text(
        weight: "bold",
        size: FONTSIZE.小四, // 正文字号
      )
      block(
        above: above,
        below: below,
        pad(
          left: indent,
          {
            set text(font: FontHeiCN, size: size)
            number
            set text(font: FontHei, size: size)
            it.body
          },
        ),
      )
    } else {
      it
    }
  }

  show heading.where(level: 1): set align(center)

  // 目录
  set page(
    numbering: "I",
    footer: context {
      [
        #align(center)[
          #text(font: FontEnglish, size: FONTSIZE.小五)[
            #counter(page).display()
          ]
        ]
      ]
    },
  )
  counter(page).update(1)

  align(center)[
    #text(font: FontHeiCN, weight: "bold", /*tracking: 2em, */ size: FONTSIZE.三号, [目录\ \ ]) // 2026模板移除了标题的2em空格
  ]
  show outline.entry: it => {
    set par(first-line-indent: 0em, leading: 0.85em)
    let indent = (it.level - 1) * 2em
    let elem = it.element
    let loc = elem.location()
    let body = elem.body
    if not elem.outlined {
      return
    }

    link(loc, {
      if it.level == 1 {
        text(
          font: FontHei,
          size: FONTSIZE.小四,
          if elem.numbering != none {
            numbering(elem.numbering, ..counter(heading).at(loc))
            h(0.5em, weak: true)
          }
            + body,
        )
      } else {
        h(indent)
        numbering(elem.numbering, ..counter(heading).at(loc))
        h(0.5em)
        body
      }

      box(width: 1fr, repeat[.])

      [#counter(page).at(loc).at(0) \ ]
    })
  }

  outline(title: none, depth: 3, indent: auto)

  set page(numbering: "1")

  // 引用
  show cite: set text(font: FontEnglish)
  show cite: it => {
    show "–": "-"
    it
  }
  // 恢复@cite的多余空格，恢复字体为英文字体

  // 页眉页脚
  set page(
    header: [
      #counter(footnote).update(0) // 重设脚注计数器，否则不同页脚注会累积
      #align(center)[
        #pad(bottom: -6pt)[
          #pad(bottom: -6pt, text(font: FontSong, size: FONTSIZE.小五, "北京邮电大学本科毕业设计（论文）"))
          #line(length: 100%, stroke: 0.5pt)
        ]
      ]
    ],
    footer: context [
      #pad(top: -13pt)[
        #align(center)[
          // 页码数字使用宋体
          #text(font: FontSongCN, size: FONTSIZE.小五)[
            #counter(page).display()
          ]
        ]
      ]
    ],
  )
  counter(page).update(1)

  // 脚注
  set footnote(numbering: "①")
  set footnote.entry(separator: none)
  show footnote: set super(baseline: -0.5em)
  show footnote.entry: it => {
    set super(size: 0.65em, baseline: -0.4em)
    show super: it => {
      it + h(3pt) // entry中序号和文本的空格
    }
    it
  }

  // 图表标题
  show figure.caption: set text(font: FontKai, size: FONTSIZE.五号)

  // 图
  show figure.where(kind: image): set figure(
    supplement: [图],
    numbering: it => {
      let chapterLevel = counter(heading).get().first()
      str(chapterLevel) + "-" + figureCounter.display() // 图序
    },
  )
  show figure.where(kind: image): set figure.caption(
    separator: h(1em), // 图序与图题之间空2个空格
  )
  show figure.where(kind: image): it => {
    figureCounter.step() // 计数器递增
    it
  }

  // 表
  show figure.where(kind: table): set figure(
    supplement: [表],
    numbering: it => {
      let chapterLevel = counter(heading).get().first()
      str(chapterLevel) + "-" + tableCounter.display() // 表序
    },
  )
  show figure.where(kind: table): set figure.caption(
    separator: h(1em), // 表序与图题之间空2个空格
    position: top,
  )
  show figure.where(kind: table): it => {
    tableCounter.step() // 计数器递增
    it
  }
  set table(
    stroke: (x, y) => if y == 0 {
      (top: 0.5pt, bottom: 0.5pt) // 首行顶/底分割线
    },
    inset: 5.8pt,
  )
  set table.hline(stroke: 0.5pt)

  // 表格后处理：可选表注
  show figure.where(kind: table): it => context {
    let next-figs = query(selector(figure.where(kind: table)).after(here()))
    let next-fig-loc = if next-figs.len() > 0 {
      next-figs.first().location()
    } else {
      none
    }
    let sel = if next-fig-loc == none {
      selector(metadata).after(here())
    } else {
      selector(metadata).after(here()).before(next-fig-loc)
    }
    let metas = query(sel)
    let notes = metas.filter(s => s.value.role == "tablenote").map(s => s.value.body)
    let note = if notes.len() > 0 { notes.first() } else { none }

    if note != none {
      block[
        #it
        #v(3pt, weak: true) // 表注和表的距离
        #layout(size => {
          // 获取父元素宽度，否则当传入相对长度时measure按照无限大计算
          let m = measure(width: size.width, it)
          // 固定宽度盒子，避免撑大
          box(width: m.width)[
            #align(left)[
              #set par(first-line-indent: 0em) // 移除表注的首行缩进
              #text(size: 0.9em)[注：#note]
            ]
          ]
        })
        #let width = measure(it).width

      ]
    } else {
      it
    }
  }

  // 算法
  show figure.where(kind: "algorithm"): set figure(
    supplement: [算法],

    numbering: it => {
      let chapterLevel = counter(heading).get().first()
      str(chapterLevel) + "-" + algorithmCounter.display() // 算法序
    },
  )
  show figure.where(kind: "algorithm"): set figure.caption(
    separator: h(1em),
  )
  show figure.where(kind: "algorithm"): it => {
    algorithmCounter.step() // 计数器递增
    it
  }
  show figure.caption.where(kind: "algorithm"): []
  show figure.where(kind: "algorithm"): it => {
    set table.cell(align: left)
    table(
      columns: (1fr,),
      {
        let chapterLevel = counter(heading).get().first()
        it.supplement
        str(chapterLevel) + "-" + algorithmCounter.display()
        h(0.5em)
        it.caption.body
      },
      it.body,
      table.hline(),
    )
  }

  // 正文
  body
}

// 附录部分
#let Appendix(
  bibliographyFile: none,
  body,
) = {
  set heading(numbering: none)
  let subheadings = heading.where(level: 2).or(heading.where(level: 3)).or(heading.where(level: 4))
  show subheadings: set heading(outlined: false)

  // 参考文献
  if bibliographyFile != none {
    [= 参考文献]

    set text(
      font: FontSong,
      size: FONTSIZE.五号,
      lang: "zh",
    )
    set par(first-line-indent: 0em)
    bibliography(
      bibliographyFile,
      title: none,
      style: "gb-7714-2015-numeric",
    )
    show bibliography: it => {}
  }

  body
}

// 表注
#let tablenote(body) = metadata((role: "tablenote", body: body))

#let algo = algo.with(
  indent-size: 1.5em,
  line-numbers: false,
  stroke: none,
  fill: none,
  block-align: left,
)

#let Achevements(body) = {
  set enum(numbering: "[1]")
  set heading(outlined: false)
  show heading.where(level: 2): it => {
    set par(first-line-indent: 0em)
    set text(font: FontHeiCN, size: FONTSIZE.四号, weight: "bold")
    block(
      above: 1.5em,
      below: 1.5em,
      it.body,
    )
  }
  body
  // 不额外补最后的空页。
}

#let cite-inline(key) = cite(key, style: "numeric-inline.csl")
