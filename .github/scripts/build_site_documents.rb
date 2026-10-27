#!/usr/bin/env ruby
# Render the two canonical Markdown documents and the user guide without runtime JS.
require 'cgi'
require 'pathname'
ROOT = Pathname.new(__dir__).join('../..').realpath
DOCS = ROOT.join('docs')
CHECK = ARGV.include?('--check')
def escape(text)
  CGI.escapeHTML(text)
end
def slug(text)
  text.downcase.gsub(/[^a-z0-9]+/, '-').gsub(/^-|-$/, '')
end
def inline(text)
  tokens = []
  protect = ->(html) { tokens << html; "TOKENPLACEHOLDER#{tokens.length - 1}END" }
  text = text.gsub(/`([^`]+)`/) { protect.call("<code>#{escape($1)}</code>") }
  text = text.gsub(/\[([^\]]+)\]\(([^)]+)\)/) do
    label, url = $1, $2
    raise "Unsupported link #{url}" unless url.match?(/\A(?:https:\/\/|mailto:|[a-z][a-z0-9.-]*\.html(?:#[-a-z0-9]+)?\z)/)
    protect.call("<a href=\"#{escape(url)}\">#{escape(label)}</a>")
  end
  text = escape(text).gsub(/\*\*([^*]+)\*\*/, '<strong>\1</strong>')
  text.gsub(/TOKENPLACEHOLDER(\d+)END/) { tokens[$1.to_i] }
end

def render(markdown)
  output, toc, paragraph, list, code = [], [], [], nil, nil
  section_open = false
  flush = -> { unless paragraph.empty?; output << "<p>#{inline(paragraph.join(' '))}</p>"; paragraph.clear; end }
  close_list = -> { if list; output << "</#{list}>"; list = nil; end }
  markdown.each_line do |raw|
    line = raw.chomp
    if code
      if line.start_with?('```')
        output << "<pre><code>#{escape(code.join("\n"))}</code></pre>"; code = nil
      else
        code << line
      end
      next
    end
    if line.start_with?('```')
      flush.call; close_list.call; code = []; next
    end
    if line.start_with?('# ')
      next
    elsif (heading = /\A(\#{2,4}) (.+)\z/.match(line))
      flush.call; close_list.call
      depth, title = heading[1].length, heading[2]
      id = slug(title)
      if depth == 2
        output << '</section>' if section_open
        output << "<section id=\"#{id}\">"; section_open = true; toc << [id, title]
      end
      output << "<h#{depth}#{depth == 2 ? '' : " id=\"#{id}\""}>#{inline(title)}</h#{depth}>"
    elsif (item = /\A(?:- |\d+\. )(.+)\z/.match(line))
      flush.call
      type = line.start_with?('- ') ? 'ul' : 'ol'
      close_list.call if list && list != type
      unless list; list = type; output << "<#{list}>"; end
      output << "<li>#{inline(item[1])}</li>"
    elsif line.empty?
      flush.call; close_list.call
    else
      close_list.call; paragraph << line
    end
  end
  flush.call; close_list.call
  raise 'Unclosed code fence' if code
  output << '</section>' if section_open
  [output.join("\n"), toc]
end
index = DOCS.join('index.html').read
header = index[/<header class="site-header">.*?<\/header>/m].sub('<a href="#explore">Explore</a>', '<a href="./">Overview</a>')
footer = index[/<footer class="site-footer">.*?<\/footer>/m]
pages = [
  ['documentation', DOCS.join('guide.md'), 'The Halthy guide.', 'From your first dashboard to your own connected setup. Clear steps, useful details, no guesswork.', 'Guide', 'Guide'],
  ['support', ROOT.join('SUPPORT.md'), 'A little help goes a long way.', 'Troubleshooting, common questions and a direct way to get in touch.', 'Support', 'Support'],
  ['privacy', ROOT.join('PRIVACY.md'), 'Your data. Your choice.', 'The complete Halthy privacy policy, reproduced from the repository source.', 'Privacy', nil]
]
failed = false
pages.each do |name, source, title, lead, label, current|
  body, toc = render(source.read)
  if name == 'support'
    body = body.sub(/(<section id="common-questions">.*?<h2>.*?<\/h2>)(.*?)(<\/section>)/m) do
      intro, questions, ending = $1, $2, $3
      questions = questions.gsub(/<h3 id="([^"]+)">(.+?)<\/h3>(.*?)(?=<h3 |\z)/m) do
        "<details id=\"#{$1}\"><summary>#{$2}</summary>#{$3}</details>"
      end
      intro + questions + ending
    end
  end
  nav = header.dup
  nav = nav.sub("href=\"#{name}.html\"", "href=\"#{name}.html\" aria-current=\"page\"") if current
  links = toc.map { |id, text| "<a href=\"##{id}\">#{escape(text)}</a>" }.join("\n")
  contact = name == 'support' ? '<div class="wrap contact-strip"><a class="button primary" href="mailto:tsdeveloper@pm.me">Email support</a><a class="button secondary" href="https://github.com/Mosher23/Halthy/issues">Report an issue on GitHub</a></div>' : ''
  policy_note = name == 'privacy' ? '<aside class="note"><p><strong>About this website:</strong> GitHub Pages hosts this static site. It has no forms, analytics, cookies set by Halthy or client-side scripts. GitHub handles hosting requests under its own <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">privacy statement</a>. The app policy below is reproduced without changing its source wording.</p></aside>' : ''
  html = <<~HTML
    <!doctype html>
    <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Halthy #{label} - Health, workouts and connected data</title>
    <meta name="description" content="#{escape(lead)}"><meta name="theme-color" content="#151a22"><meta name="referrer" content="strict-origin-when-cross-origin">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'">
    <link rel="canonical" href="https://mosher23.github.io/Halthy/#{name}.html"><link rel="icon" href="assets/app-icon.png"><link rel="stylesheet" href="assets/site.css">
    </head><body><a class="skip-link" href="#main">Skip to content</a>#{nav}
    <main id="main"><div class="wrap"><div class="page-heading"><p class="eyebrow">HALTHY / #{label.upcase}</p><h1>#{title}</h1><p class="lead">#{escape(lead)}</p></div></div>
    #{contact}<div class="wrap doc-layout"><nav class="doc-nav" aria-label="On this page"><strong>ON THIS PAGE</strong>#{links}</nav><article class="prose" aria-label="#{label}">
    <p class="policy-source">Source: <a href="https://github.com/Mosher23/Halthy/blob/main/#{source.relative_path_from(ROOT)}">#{source.relative_path_from(ROOT)}</a></p>#{policy_note}
    #{body}</article></div></main>#{footer}</body></html>
  HTML
  target = DOCS.join("#{name}.html")
  if CHECK
    if !target.exist? || target.read != html
      warn "Out of date: #{target}"; failed = true
    end
  else
    target.write(html)
    puts "Rendered #{target.relative_path_from(ROOT)}"
  end
end
exit 1 if failed
