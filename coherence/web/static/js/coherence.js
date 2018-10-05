// Licensed under the MIT license
// http://opensource.org/licenses/mit-license.php
//
// Copyright 2018, Pol Canelles <canellestudi@gmail.com>

/*
Create Web Socket to communicate with Python Server
*/
$(document).ready(function(){
    (function() {
       if ("WebSocket" in window) {
          console.log("Your browser supports WebSocket.");

          var ws = new WebSocket("ws://127.0.0.1:9000");
          ws.binaryType = "arraybuffer";

          ws.addEventListener('open', function(e) {
             ws.send('WebSocket Ready')
             console.log("Opened WebSocket OK.");
          });

          ws.addEventListener('message', function(e) {
             try {
                var msg = JSON.parse(e.data);
                if (msg.type.match("^log-")) {
                   //console.log('add log: ' + msg.type)
                    $( ".log-box" ).append(
                        '<p class="' + msg.type + ' left-1">' +
                        msg.data + '</p>' );
                } else if (msg.type == "add-device") {
                   console.log('add device: ' + msg.name)
                    $( "#devices-list" ).append(
                        '<li data-usn="' + msg.usn + '"><a class="coherence_menu_link" ' +
                        'href="#" onclick="openLink(\''+ msg.link +'\', this)">' +
                        msg.name + '</a></li>' );
                } else if (msg.type == "remove-device") {
                   console.log('remove device with usn: ' + msg.usn)
                   $("#devices-list > :li[data-usn='" + msg.usn + "']").remove();
                }
             } catch(err) {
                console.log('error on parsing message: ' + e.data);
                $( ".log-box" ).append( '<p class="left-1">' + e.data + '</p>' );
             }
             //ws.close();
          });

          ws.addEventListener('error', function(err) {
             console.log('WebSocket Error: ', err);
          });

          ws.addEventListener('close', function(e) {
             console.log("WebSocket connection closed.");
          });
       }
       else {
          console.log("Your browser does not support WebSocket.");
       }
    })();
});

/*
Functions to browse servers content
*/
function openLinkInTab(url) {
    var win = window.open(url);
    if (win) {
        //Browser has allowed it to be opened
        win.focus();
    } else {
        //Browser has blocked it
        alert('Please allow popups for this website');
    }
}

function openLink(url, element) {
    if (url.match(/.xml$/)){
        console.log('It is an xml file (open in new tab)');
        openLinkInTab(url);
        return false;
    }
    console.log('openLink: ' + url);
    $('.devices-box').empty();
    $('div.devices-box').load(url, function(){
        if( $('.devices-box').is(':empty') ) {
            console.log('Cannot load url internally, trying to' +
                        'load into new tab: ' + url);
            openLinkInTab(url);
        } else {
            console.log('Ok loaded url: ' + url);
            }
    });
}

/*
Show/hide content depending on navigation bar selection
*/
function openTab(pageName, element) {
    var i, tabcontent, tablinks;
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    tablinks = document.getElementsByClassName("tablink");
    for (i = 0; i < tablinks.length; i++) {
        $(tablinks[i]).parent().removeClass("active");
    }
    console.log('Trying to find tab: ' + pageName)
    document.getElementById(pageName).style.display = "block";
    $(element).parent().addClass("active");
}