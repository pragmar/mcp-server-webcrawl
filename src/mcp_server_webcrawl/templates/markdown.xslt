<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <xsl:output method="text"/>

    <xsl:template match="/">
        <xsl:apply-templates/>
    </xsl:template>

    <xsl:template name="structural">
        <xsl:choose>
            <xsl:when test="ancestor::li or ancestor::td or ancestor::th or ancestor::dd">true</xsl:when>
            <xsl:otherwise>false</xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template name="heading">
        <xsl:param name="prefix"/>
        <xsl:if test="normalize-space(.) != ''">
            <xsl:text>&#10;&#10;</xsl:text>
            <xsl:value-of select="$prefix"/>
            <xsl:text> </xsl:text>
            <xsl:value-of select="normalize-space(.)"/>
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="h1">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">#</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="h2">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">##</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="h3">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">###</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="h4">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">####</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="h5">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">#####</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="h6">
        <xsl:call-template name="heading">
            <xsl:with-param name="prefix">######</xsl:with-param>
        </xsl:call-template>
    </xsl:template>

    <xsl:template match="strong | b">
        <!-- proper whitespace handling for preceding/following sibling text -->
        <xsl:if test="normalize-space(.) != ''">
            <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
                <xsl:text> </xsl:text>
            </xsl:if>
            <xsl:text>**</xsl:text><xsl:apply-templates/><xsl:text>**</xsl:text>
            <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
                <xsl:text> </xsl:text>
            </xsl:if>
        </xsl:if>
    </xsl:template>

    <xsl:template match="em | i">
        <xsl:if test="normalize-space(.) != ''">
            <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
                <xsl:text> </xsl:text>
            </xsl:if>
            <xsl:text>*</xsl:text><xsl:apply-templates/><xsl:text>*</xsl:text>
            <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
                <xsl:text> </xsl:text>
            </xsl:if>
        </xsl:if>
    </xsl:template>

    <xsl:template match="ul | ol">
        <xsl:if test="not(ancestor::li) or not(preceding-sibling::li)">
            <xsl:text>&#10;</xsl:text>
        </xsl:if>
        <!-- render if there's at least one li with content -->
        <xsl:if test="normalize-space(.) != ''">
            <xsl:apply-templates select="li">
                <xsl:with-param name="list-type" select="local-name()"/>
            </xsl:apply-templates>
        </xsl:if>
    </xsl:template>

    <xsl:template match="li">

        <xsl:param name="list-type" select="'ul'"/>

        <xsl:variable name="depth" select="count(ancestor::li)"/>
        <xsl:variable name="text" select="normalize-space(.)"/>

        <!-- Add indentation -->
        <xsl:call-template name="indent">
            <xsl:with-param name="count" select="$depth * 4"/>
        </xsl:call-template>

        <!-- Add bullet or number -->
        <xsl:choose>
            <xsl:when test="not($text) and not(.//a)">
                <!-- Skip empty items entirely -->
            </xsl:when>
            <xsl:when test="$list-type = 'ul'">
                <xsl:text>* </xsl:text>
            </xsl:when>
            <xsl:when test="$list-type = 'ol'">
                <xsl:number count="li[normalize-space(.) != '']" format="1"/>
                <xsl:text>. </xsl:text>
            </xsl:when>
        </xsl:choose>
        <!-- Process all content -->
        <xsl:apply-templates/>
        <xsl:text>&#10;</xsl:text>
    </xsl:template>

    <xsl:template name="indent">
        <xsl:param name="count" select="0"/>
        <xsl:value-of select="substring('                                        ', 1, $count)"/>
    </xsl:template>

     <xsl:template match="p">
        <xsl:variable name="within-structural-container">
            <xsl:call-template name="structural"/>
        </xsl:variable>

        <xsl:if test="$within-structural-container = 'false'">
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
        <xsl:apply-templates/>
        <xsl:if test="$within-structural-container = 'false'">
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="div[not(parent::div) and not(ancestor-or-self::td)]">
        <xsl:if test="normalize-space(.) != ''">
            <xsl:text>&#10;</xsl:text>
            <xsl:apply-templates/>
        </xsl:if>
    </xsl:template>

    <xsl:template match="span/div | li/p | li/div | td/div">
        <xsl:apply-templates/>
    </xsl:template>

    <xsl:template match="span">
        <xsl:if test="normalize-space(.) != ''">
            <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
                <xsl:text> </xsl:text>
            </xsl:if>
            <xsl:value-of select="normalize-space(.)"/>
            <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
                <xsl:text> </xsl:text>
            </xsl:if>
        </xsl:if>
    </xsl:template>

    <xsl:template match="a[starts-with(@href, '#')]">
        <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
            <xsl:text> </xsl:text>
        </xsl:if>
        <xsl:value-of select="normalize-space(.)"/>
        <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
            <xsl:text> </xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="a">
        <xsl:variable name="text" select="normalize-space(.)"/>
        <xsl:variable name="href" select="normalize-space(@href)"/>
        <xsl:variable name="within-structural-container">
            <xsl:call-template name="structural"/>
        </xsl:variable>
        <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
            <xsl:text> </xsl:text>
        </xsl:if>
        <xsl:choose>
            <xsl:when test="$text != '' and $href != ''">
                <xsl:choose>
                    <xsl:when test="$within-structural-container = 'false' and (div | p | h1 | h2 | h3 | h4 | h5 | h6 | blockquote | pre)">
                        <!--
                            contains structural content inside the <a>, this is legal HTML
                            but gets into confusing and dangerous markdown territory of what
                            can be legit handled. see text2html for examples of block a handling,
                            e.g. pragmar.com homepage
                            for now handle the same as any other link, but clear with newlines
                         -->
                        <xsl:text>[</xsl:text><xsl:value-of select="$text"/><xsl:text>]</xsl:text>
                        <xsl:text>(</xsl:text><xsl:value-of select="$href"/><xsl:text>)&#10;&#10;</xsl:text>
                    </xsl:when>
                    <xsl:otherwise>
                        <xsl:text>[</xsl:text><xsl:value-of select="$text"/><xsl:text>]</xsl:text>
                        <xsl:text>(</xsl:text><xsl:value-of select="$href"/><xsl:text>)</xsl:text>
                    </xsl:otherwise>
                </xsl:choose>
            </xsl:when>
        </xsl:choose>

        <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
            <xsl:text> </xsl:text>
        </xsl:if>

    </xsl:template>

    <xsl:template match="img">
        <!-- it's almost always LLM noise, html2text removes some not all
            expect edge cases, stay flexy -->
        <!-- <xsl:variable name="src" select="normalize-space(@src)"/>
        <xsl:if test="$src != ''">
            <xsl:text>![</xsl:text><xsl:value-of select="normalize-space(@alt)"/><xsl:text>]</xsl:text>
            <xsl:text>(</xsl:text><xsl:value-of select="$src"/><xsl:text>)</xsl:text>
        </xsl:if> -->
    </xsl:template>

    <xsl:template match="pre">
        <xsl:text>&#10;&#10;```</xsl:text>
        <xsl:if test="code/@class">
            <xsl:call-template name="extract-language">
                <xsl:with-param name="class" select="code/@class"/>
            </xsl:call-template>
        </xsl:if>
        <xsl:text>&#10;</xsl:text>
        <xsl:choose>
            <xsl:when test="code">
                <xsl:value-of select="code"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:value-of select="."/>
            </xsl:otherwise>
        </xsl:choose>
        <xsl:text>&#10;```&#10;&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="code">
        <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
            <xsl:text> </xsl:text>
        </xsl:if>
        <xsl:if test="not(parent::pre)">
            <xsl:text>`</xsl:text><xsl:value-of select="."/><xsl:text>`</xsl:text>
        </xsl:if>
        <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
            <xsl:text> </xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template name="extract-language">
        <xsl:param name="class"/>
        <xsl:choose>
            <xsl:when test="starts-with($class, 'language-')">
                <xsl:value-of select="substring-after($class, 'language-')"/>
            </xsl:when>
            <xsl:when test="starts-with($class, 'lang-')">
                <xsl:value-of select="substring-after($class, 'lang-')"/>
            </xsl:when>
            <xsl:when test="contains($class, 'language-')">
                <xsl:value-of select="substring-before(substring-after($class, 'language-'), ' ')"/>
            </xsl:when>
            <xsl:when test="contains($class, 'lang-')">
                <xsl:value-of select="substring-before(substring-after($class, 'lang-'), ' ')"/>
            </xsl:when>
        </xsl:choose>
    </xsl:template>

    <xsl:template name="table-separator">
        <xsl:param name="row"/>
        <xsl:param name="type" select="'dashes'"/>
        <xsl:text>|</xsl:text>
        <xsl:for-each select="$row/th | $row/td">
            <xsl:choose>
                <xsl:when test="$type = 'dashes'">
                    <xsl:text>---|</xsl:text>
                </xsl:when>
                <xsl:when test="$type = 'empty'">
                    <xsl:text>   |</xsl:text>
                </xsl:when>
            </xsl:choose>
        </xsl:for-each>
        <xsl:text>&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="table">
        <xsl:text>&#10;&#10;</xsl:text>
        <xsl:variable name="rows" select=".//tr"/>
        <xsl:choose>
            <xsl:when test="normalize-space(.) = ''"></xsl:when>
            <xsl:when test="count($rows[1]/th) > 0">
                <xsl:apply-templates select="$rows[1]"/>
                <xsl:call-template name="table-separator">
                    <xsl:with-param name="row" select="$rows[1]"/>
                    <xsl:with-param name="type" select="'dashes'"/>
                </xsl:call-template>
                <xsl:apply-templates select="$rows[position() > 1]"/>
            </xsl:when>
            <!-- create empty header and treat all rows as data -->
            <xsl:otherwise>
                <xsl:call-template name="table-separator">
                    <xsl:with-param name="row" select="$rows[1]"/>
                    <xsl:with-param name="type" select="'empty'"/>
                </xsl:call-template>
                <xsl:call-template name="table-separator">
                    <xsl:with-param name="row" select="$rows[1]"/>
                    <xsl:with-param name="type" select="'dashes'"/>
                </xsl:call-template>
                <xsl:apply-templates select="$rows"/>
            </xsl:otherwise>
        </xsl:choose>
        <xsl:text>&#10;&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="tbody">
        <xsl:apply-templates/>
    </xsl:template>

    <xsl:template match="tr">
        <xsl:text>|</xsl:text>
        <xsl:apply-templates select="th | td"/>
        <xsl:text>&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="th | td">
        <xsl:variable name="content" select="normalize-space(.)"/>
        <xsl:text> </xsl:text>
        <xsl:choose>
            <xsl:when test="$content != ''">
                <xsl:apply-templates/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:text> </xsl:text>
            </xsl:otherwise>
        </xsl:choose>
        <xsl:text> |</xsl:text>
    </xsl:template>

    <xsl:template match="blockquote">
        <xsl:text>&#10;&#10;</xsl:text>
        <xsl:call-template name="blockquote-content">
            <xsl:with-param name="content" select="."/>
        </xsl:call-template>
        <xsl:text>&#10;&#10;</xsl:text>
    </xsl:template>

    <xsl:template name="blockquote-content">
        <xsl:param name="content"/>
        <xsl:call-template name="split-lines">
            <xsl:with-param name="text" select="normalize-space($content)"/>
        </xsl:call-template>
    </xsl:template>

    <xsl:template name="split-lines">
        <xsl:param name="text"/>
        <xsl:choose>
            <xsl:when test="contains($text, '&#10;')">
                <xsl:text>&gt; </xsl:text>
                <xsl:value-of select="substring-before($text, '&#10;')"/>
                <xsl:text>&#10;</xsl:text>
                <xsl:call-template name="split-lines">
                    <xsl:with-param name="text" select="substring-after($text, '&#10;')"/>
                </xsl:call-template>
            </xsl:when>
            <xsl:when test="normalize-space($text)">
                <xsl:text>&gt; </xsl:text>
                <xsl:value-of select="$text"/>
                <xsl:text>&#10;</xsl:text>
            </xsl:when>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="hr">
        <xsl:text>&#10;&#10;---&#10;&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="br">
        <xsl:text>  &#10;</xsl:text>
    </xsl:template>

    <xsl:template match="del | s | strike">
        <xsl:if test="normalize-space(.) != ''">
            <xsl:if test="preceding-sibling::text()[1][substring(., string-length(.)) = ' ']">
                <xsl:text> </xsl:text>
            </xsl:if>
            <xsl:text>~~</xsl:text><xsl:apply-templates/><xsl:text>~~</xsl:text>
            <xsl:if test="following-sibling::text()[1][starts-with(., ' ')]">
                <xsl:text> </xsl:text>
            </xsl:if>
        </xsl:if>
    </xsl:template>

    <xsl:template match="dl">
        <xsl:text>&#10;</xsl:text>
        <xsl:apply-templates/>
        <xsl:text>&#10;</xsl:text>
    </xsl:template>

    <xsl:template match="dt">
        <xsl:variable name="within-structural-container">
            <xsl:call-template name="structural"/>
        </xsl:variable>

        <xsl:if test="$within-structural-container = 'false'">
            <xsl:text>&#10;</xsl:text>
        </xsl:if>
        <xsl:text>**</xsl:text><xsl:apply-templates/><xsl:text>**</xsl:text>
        <xsl:if test="$within-structural-container = 'false'">
            <xsl:text>&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="dd">
        <xsl:variable name="within-structural-container">
            <xsl:call-template name="structural"/>
        </xsl:variable>

        <xsl:choose>
            <xsl:when test="$within-structural-container = 'true'">
                <xsl:text>: </xsl:text><xsl:apply-templates/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:text>    </xsl:text><xsl:apply-templates/><xsl:text>&#10;</xsl:text>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="div">
        <xsl:apply-templates/>
        <xsl:if test="not(ancestor::table)">
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="script | style | svg | head | meta | title | link | input | select | textarea | base | object | embed | param | applet | canvas | audio | video | source | track | noscript | template | wbr | bdi | bdo | ruby | rt | rp | details | summary | dialog | menu | menuitem | slot">
    </xsl:template>

    <xsl:template match="text()">
        <xsl:value-of select="normalize-space(.)"/>
        <xsl:if test="(not(ancestor::li) and following-sibling::ul) or following-sibling::ol or following-sibling::table">
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

    <xsl:template match="*">
        <xsl:variable name="isOwnLine" select="not(ancestor::li) or following-sibling::*[self::ul or self::ol]"/>
        <xsl:if test="$isOwnLine">
            <xsl:text>&#10;&#10;</xsl:text>
        </xsl:if>
        <xsl:apply-templates/>
        <xsl:if test="$isOwnLine">
            <xsl:text>&#10;</xsl:text>
        </xsl:if>
    </xsl:template>

</xsl:stylesheet>