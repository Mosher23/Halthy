#!/usr/bin/env ruby
# Render the two canonical Markdown documents and the user guide without runtime JS.
require 'cgi'
require 'pathname'
require 'json'
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
releases = JSON.parse(DOCS.join('releases.json').read).fetch('releases')
release_nav = releases.map { |r| "<a href=\"#v#{r.fetch('version').tr('.', '-')}\"><span>v#{escape(r.fetch('version'))}</span><small>#{escape(r.fetch('date_label'))}</small></a>" }.join
entries = releases.each_with_index.map do |r, index|
  id = "v#{r.fetch('version').tr('.', '-')}"
  groups = r.fetch('groups').map do |g|
    items = g.fetch('items').map { |item| "<li>#{escape(item)}</li>" }.join
    "<section class=\"release-group\"><p class=\"release-category\">#{escape(g.fetch('label'))}</p><h3>#{escape(g.fetch('title'))}</h3><ul>#{items}</ul></section>"
  end.join
  visual = r['image'] ? "<figure class=\"release-visual\"><img src=\"#{escape(r.fetch('image'))}\" width=\"720\" height=\"1565\" alt=\"#{escape(r.fetch('image_alt'))}\" fetchpriority=\"high\"><figcaption>Halthy 1.2 / demonstration data</figcaption></figure>" : ''
  <<~HTML
    <article class="release-entry#{index.zero? ? ' release-featured' : ''}" id="#{id}" aria-labelledby="#{id}-title">
    <div class="release-rail"><a class="release-version" href="##{id}" aria-label="Link to version #{escape(r.fetch('version'))}">#{escape(r.fetch('version'))}</a><time datetime="#{escape(r.fetch('date'))}">#{escape(r.fetch('date_label'))}</time><span class="release-kind#{r.fetch('status') == 'planned' ? ' is-planned' : ''}">#{escape(r.fetch('label'))}</span></div>
    <div class="release-card"><div class="release-intro#{visual.empty? ? '' : ' has-visual'}"><div><p class="eyebrow">#{index.zero? ? 'THE NEXT CHAPTER' : 'THE STORY SO FAR'}</p><h2 id="#{id}-title">#{escape(r.fetch('title'))}</h2><p class="release-summary">#{escape(r.fetch('summary'))}</p>#{index.zero? ? '<a class="text-link" href="documentation.html">Explore the Halthy guide <span aria-hidden="true">&#8599;</span></a>' : ''}</div>#{visual}</div><div class="release-groups">#{groups}</div><p class="release-note">#{escape(r.fetch('note'))}</p></div></article>
  HTML
end.join
changelog_header = header.sub('href="changelog.html"', 'href="changelog.html" aria-current="page"')
changelog_html = <<~HTML
  <!doctype html>
  <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Halthy Changelog - Every update, thoughtfully made</title><meta name="description" content="What's new in Halthy for iPhone. Explore release dates, design changes, features and improvements in versions 1.0, 1.1 and 1.2.">
  <meta name="theme-color" content="#151a22"><meta name="referrer" content="strict-origin-when-cross-origin"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'">
  <link rel="canonical" href="https://mosher23.github.io/Halthy/changelog.html"><link rel="icon" href="assets/app-icon.png"><link rel="stylesheet" href="assets/site.css">
  <meta property="og:type" content="website"><meta property="og:title" content="Halthy - The story keeps getting better"><meta property="og:description" content="A record of the features, refinements and little details that make Halthy better."><meta property="og:url" content="https://mosher23.github.io/Halthy/changelog.html">
  </head><body><a class="skip-link" href="#main">Skip to content</a>#{changelog_header}<main id="main">
  <header class="wrap changelog-heading"><p class="eyebrow"><span class="live-dot" aria-hidden="true"></span>HALTHY / CHANGELOG</p><h1>The story keeps<br><span>getting better.</span></h1><div class="changelog-lead"><p class="lead">New ideas. Thoughtful refinements. The little details that make Halthy feel more like you. Here&#8217;s everything that&#8217;s changing.</p><span class="changelog-count">03<span>chapters so far</span></span></div></header>
  <nav class="wrap release-jump" aria-label="Jump to a release">#{release_nav}</nav>
  <div class="wrap release-timeline">#{entries}</div>
  <aside class="wrap changelog-end"><span class="release-end-mark" aria-hidden="true">&#10022;</span><h2>Made better, together.</h2><p>Have an idea, a small frustration or something you&#8217;d love to see next? We&#8217;re listening.</p><a class="button secondary" href="support.html">Share your feedback <span aria-hidden="true">&#8599;</span></a></aside>
  </main>#{footer}</body></html>
HTML
target = DOCS.join('changelog.html')
if CHECK
  if !target.exist? || target.read != changelog_html
    warn "Out of date: #{target}"; failed = true
  end
else
  target.write(changelog_html)
  puts "Rendered #{target.relative_path_from(ROOT)}"
end
exit 1 if failed
