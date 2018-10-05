$("div.devices-box").on('click', 'a', function(event){
    if (this.href === '#'){
        return true;
    }

    event.preventDefault()
    event.stopPropagation();

    if ($(this).hasClass( "item-audio" )){
        openLinkInTab(this.href);
        return false;
    } else if ($(this).hasClass( "item-image" )){
        openLinkInTab(this.href);
        return false;
    } else if ($(this).hasClass( "item-video" )){
        openLinkInTab(this.href);
        return false;
    }

    console.log('current href is: ' + this.href);
    var link = this.href;
    this.href = "#"
    console.log('new href is: ' + this.href);
    openLink(link, this)
    return false;
});