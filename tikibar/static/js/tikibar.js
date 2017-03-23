// Function.bind support for older browsers:
Function.prototype.bind = Function.prototype.bind || function(d) {
    var a=Array.prototype.splice.call(arguments,1),c=this;
    var b=function(){
        var e=a.concat(Array.prototype.splice.call(arguments,0));
        if(!(this instanceof b)){
            return c.apply(d,e)
        }
        c.apply(this,e)
    };
    b.prototype=c.prototype;
    return b;
};

jQuery(window).on('load', function() {
    // Poll until tikibar_host is available
    var interval = setInterval(function() {
        if (window.tikibar_host) {
            tikibar_host.send_performance_data();
            clearInterval(interval);        
        }
    }, 100);
});

var domainRegex = /^(https?:\/\/)?([-\w]+\.)*([-\w]+\.(com|ca|co\.uk|ie|de|es|fr|it|nl|pt|sv|co\.nz|com\.au|hk|sg|in|com\.br))(\/.*)?$/;
function extractDomain(url) {
    var originMatches = url.match(domainRegex);
    return originMatches && originMatches[3];
}

jQuery(function($) {
    function TikibarHost(options) {
        if (this == window) {
            return new TikibarHost(options);
        }
        options = options || {};
        var attach = options.attach || document.body;

        jQuery('#tikibar_iframe_container').remove();
        var div = jQuery('<div id="tikibar_iframe_container"><iframe width="100%" height="100%"></iframe></div>');
        this.iframe = div.find('iframe')[0];
        this.container = div[0];
        div.height(60);
        div.find('iframe').height(60); // For mobile safari
        // We position absolute / zindex the iframe to prevent the box shadow 
        // on the autocomplete box in the eventbrite header from overlapping the tikibar
        div.find('iframe').css({
            position: 'absolute',
            zIndex: 1000
        });
        div.find('iframe').attr('src', this.get_tikibar_url());
        div.prependTo(attach);
        $(attach).css({
            position: 'absolute',
            width: '100%',
            top: '60px',
            margin: 0
        });
        div.css({
            marginTop: '-60px'
        });

        // Recieve messages from the child frame
        window.addEventListener('message', this.recieve_message.bind(this));

        // Listen to jQuery Ajax calls
        jQuery(document).bind('ajaxComplete', this.on_ajax_request.bind(this));

        // Listen to fetch() calls too
        var self = this;
        if (window.fetch && window.Promise) {
            var original_fetch = window.fetch;
            window.fetch = function(input, init) {
                return original_fetch(input, init).then(function(response) {
                    var method = (init || {}).method || 'GET';
                    var correlation_id = response.headers.get('x-correlation-id');
                    var tiki_time = parseFloat(response.headers.get('x-tiki-time') || '0');
                    self.send_message({
                        'tiki_msg_type': 'ajax_request',
                        'url': input,
                        'verb': method, // GET or POST
                        'status_code': response.status,
                        'ms': tiki_time * 1000,
                        'correlation_id': correlation_id
                    });
                    return Promise.resolve(response);
                });
            }
        }

    }

    TikibarHost.prototype.recieve_message = function(event) {
        var originDomain = extractDomain(event.origin);
        var currentDomain = extractDomain(location.host);

        if (originDomain != currentDomain) {
            return;
        }

        var data = JSON.parse(event.data);
        if (data.tiki_msg_type == 'height') {
            jQuery(this.container).add(this.iframe).height(data.height);
        }
        if (data.tiki_msg_type == 'hide') {
            jQuery(this.container).remove();
        }
    }

    TikibarHost.prototype.send_message = function(msg) {
        this.iframe.contentWindow.postMessage(JSON.stringify(msg), '*');
    }

    TikibarHost.prototype.send_performance_data = function() {
        // Create a copy of window.performance.timings
        var copy = {};
        var ok = false;
        var timing = (window.performance && window.performance.timing) || {};
        jQuery.each(timing, function(name, timestamp) {
            if (!jQuery.isNumeric(timestamp)) {
                return true; // Skip this one (e.g. toJSON on Firefox)
            }
            ok = true;
            copy[name] = timestamp;
        });
        if (ok) {
            this.send_message({
                'tiki_msg_type': 'performance_timing',
                'timing': copy
            });
        }
    }

    TikibarHost.prototype.get_tikibar_url = function() {
        var correlation_id = document.getElementsByName('correlation_id')[0].getAttribute('value');
        var url = window.TIKI_PROTOCOL + '://' + location.host + '/tikibar/?correlation_id=' + correlation_id + '&render=1&run_js=1';
        return url;
    };

    TikibarHost.prototype.on_ajax_request = function(event, xhr, settings) {
        this.send_message({
            'tiki_msg_type': 'ajax_request',
            'url': settings.url,
            'verb': settings.type, // GET or POST
            'status_code': xhr.status,
            'ms': xhr.getResponseHeader('X-Tiki-Time') * 1000,
            'correlation_id': xhr.getResponseHeader('X-Correlation-ID')
        });
    }

    window.tikibar_host = TikibarHost({attach: document.body});

});

