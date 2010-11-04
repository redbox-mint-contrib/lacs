import md5

from au.edu.usq.fascinator.api.indexer import SearchRequest
from au.edu.usq.fascinator.common import JsonConfigHelper
from au.edu.usq.fascinator.portal.services import PortalManager

from java.io import ByteArrayInputStream, ByteArrayOutputStream, InputStreamReader
from java.lang import Exception, String
from java.util import ArrayList, HashMap, HashSet, LinkedHashMap

from org.apache.commons.lang import StringEscapeUtils

class NameAuthorityData:
    def __activate__(self, context):
        self.log = context["log"]
        self.services = context["Services"]
        self.formData = context["formData"]
        self.response = context["response"]
        self.defaultPortal = context["defaultPortal"]
        self.sessionState = context["sessionState"]
        
        self.__oid = self.formData.get("oid")
        try:
            # get the package manifest
            self.__manifest = self.__readManifest(self.__oid)
            self.__metadata = self.__getMetadata(self.__oid)
        except Exception, e:
            self.log.error("Failed to load manifest: {}", e.getMessage());
            raise e
        
        #print "\n***************\n%s\n************\n" % self.sessionState
        self.__oidList, self.__nameList = self.__getNavData()
        
        result = None
        try:
            func = self.formData.get("func")
            if func == "link-names":
                ids = self.formData.getValues("ids")
                records = self.__getAuthorDetails(ids)
                result = self.__linkNames(records)
            elif func == "unlink-names":
                ids = self.formData.getValues("ids")
                result = self.__unlinkNames(ids)
            #self.log.info(self.__manifest.toString())
            elif func== "search-names":
                searchText = self.formData.get("text")
                result = self.__searchNames(searchText)
        except Exception, e:
            result = '{ status: "error", message: "%s" }' % str(e)
        if result:
            writer = self.response.getPrintWriter("application/json; charset=UTF-8")
            writer.println(result)
            writer.close()
            
    def __linkNames(self, records):
        for record in records:
            id = record.get("id")
            name = record.getList("dc_title").get(0)
            title = record.getList("dc_description").get(0)
            handle = record.getList("handle").get(0)
            faculty = record.getList("faculty").get(0)
            school = record.getList("school").get(0)
            hash = self.getHash(name)
            self.__manifest.set("manifest/node-%s/title" % (hash), name)
            self.__manifest.set("manifest/node-%s/children/node-%s/id" % (hash, id), id)
            self.__manifest.set("manifest/node-%s/children/node-%s/title" % (hash, id), title)
            if handle:
                self.__manifest.set("manifest/node-%s/children/node-%s/handle" % (hash, id), handle)
            if faculty:
                self.__manifest.set("manifest/node-%s/children/node-%s/faculty" % (hash, id), faculty)
            if school:
                self.__manifest.set("manifest/node-%s/children/node-%s/school" % (hash, id), school)
        self.__saveManifest(self.__oid)
        return '{ status: "ok" }'
    
    def __unlinkNames(self, ids):
        for id in ids:
            self.__manifest.removePath("//children/node-%s" % id)
            print self.__manifest
        self.__saveManifest(self.__oid)
        return '{ status: "ok" }'
    
    def __getNavData(self):
        query = self.sessionState.get("query")
        if query == "":
            query = "*:*"
        req = SearchRequest(query)
        req.setParam("fl", "id dc_title")
        req.setParam("sort", "f_dc_title asc")
        req.setParam("rows", "10000")
        fq = self.sessionState.get("fq")
        if fq:
            for q in fq:
                req.addParam("fq", q)
        
        out = ByteArrayOutputStream()
        indexer = self.services.getIndexer()
        indexer.search(req, out)
        result = JsonConfigHelper(ByteArrayInputStream(out.toByteArray()))
        oidList = result.getList("response/docs/id")
        nameList = result.getList("response/docs/dc_title")
        #print " *** oidList:'%s'" % oidList
        #print " *** nameList:'%s'" % nameList
        return oidList, nameList
    
    def __getNavDataUnedited(self):
        pass
    
    def __getIndex(self):
        return self.__oidList.indexOf(self.__oid)
    
    def getNextOid(self):
        i = self.__getIndex()
        if i+1 < self.__oidList.size():
            return self.__oidList.get(i+1)
        return None
    
    def getNextName(self):
        i = self.__getIndex()
        if i+1 < self.__nameList.size():
            return self.__nameList.get(i+1)
        return None
    
    def getPrevOid(self):
        i = self.__getIndex()
        if i > 0:
            return self.__oidList.get(i-1)
        return None
    
    def getPrevName(self):
        i = self.__getIndex()
        if i > 0:
            return self.__nameList.get(i-1)
        return None
    
    def getNextUneditedOid(self):
        return None
    
    def getNextUneditedName(self):
        return None
    
    def getPrevUneditedOid(self):
        return None
    
    def getPrevUneditedName(self):
        return None
    
    def getHash(self, data):
        return md5.new(data).hexdigest()
    
    def __getAuthorDetails(self, authorIds):
        query = " OR id:".join(authorIds)
        req = SearchRequest('id:%s' % query)
        req.setParam("fq", 'recordtype:"author"')
        req.addParam("fq", 'item_type:"object"')
        req.setParam("rows", "9999")
        
        # Make sure 'fq' has already been set in the session
        ##security_roles = self.authentication.get_roles_list();
        ##security_query = 'security_filter:("' + '" OR "'.join(security_roles) + '")'
        ##req.addParam("fq", security_query)
        
        out = ByteArrayOutputStream()
        indexer = self.services.getIndexer()
        indexer.search(req, out)
        result = JsonConfigHelper(ByteArrayInputStream(out.toByteArray()))
        return result.getJsonList("response/docs")
    
    def isLinked(self, oid):
        node = self.__manifest.get("manifest//node-%s" % oid)
        #self.log.info("manifest:{}", self.__manifest)
        #self.log.info(" ******* nodeid: {}", node)
        return node is not None
    
    def getSuggestedNames(self):
        # search common forms
        lookupNames = []
        surname = self.__metadata.getList("surname").get(0)
        firstName = self.__metadata.getList("firstName").get(0)
        firstInitial = firstName[0].upper()
        secondName = self.__metadata.getList("secondName")
        if not secondName.isEmpty():
            secondName = secondName.get(0)
        if secondName and secondName != "":
            secondInitial = secondName[0].upper()
            lookupNames.append("%s, %s. %s." % (surname, firstInitial, secondInitial))
            lookupNames.append("%s, %s %s." % (surname, firstName, secondInitial))
            lookupNames.append("%s, %s %s" % (surname, firstName, secondName))
            lookupNames.append("%s %s %s" % (firstName, secondName, surname))
        lookupNames.append("%s, %s." % (surname, firstInitial))
        lookupNames.append("%s, %s" % (surname, firstName))
        lookupNames.append("%s %s" % (firstName, surname))
        query = '" OR dc_title:"'.join(lookupNames)
        
        # general word search from each part of the name
        parts = [p for p in self.getPackageTitle().split(" ") if len(p) > 0]
        query2 = " OR dc_title:".join(parts)
        
        
        #filter out the linked citation
        linkedCitations = self.__manifest.getList("//children//id")
        query3 = ""
        if linkedCitations:
            query3 = " OR ".join(linkedCitations)
            query3 = " AND -id:(%s)" % query3
        
        req = SearchRequest('(dc_title:"%s")^2.5 OR (dc_title:%s)^0.5%s' % (query, query2, query3))
        self.log.info("suggestedNames query={}", req.query)
        req.setParam("fq", 'recordtype:"author"')
        req.addParam("fq", 'item_type:"object"')
        req.setParam("rows", "9999")
        req.setParam("fl", "score")
        req.setParam("sort", "score desc")
        
        # Make sure 'fq' has already been set in the session
        ##security_roles = self.authentication.get_roles_list();
        ##security_query = 'security_filter:("' + '" OR "'.join(security_roles) + '")'
        ##req.addParam("fq", security_query)
        
        out = ByteArrayOutputStream()
        indexer = self.services.getIndexer()
        indexer.search(req, out)
        result = JsonConfigHelper(ByteArrayInputStream(out.toByteArray()))
        
        #self.log.info("result={}", result.toString())
        docs = result.getJsonList("response/docs")
        
        exactMatchRecords = LinkedHashMap()
        map = LinkedHashMap()
        for doc in docs:
            authorName = doc.getList("dc_title").get(0)
            rank = self.getRank(doc.getList("score").get(0))
            if map.containsKey(authorName):
                authorDocs = map.get(authorName)
            else:
                authorDocs = ArrayList()
                map.put(authorName, authorDocs)
            authorDocs.add(doc)
            
            if float(rank) == 100.00:
                exactMatchRecords.put(authorName, authorDocs)
                map.remove(authorName)
        
        self.__maxScore = max(1.0, float(result.get("response/maxScore")))
        
        #NOTE!!! only the first time (workflow_modified is false)
        self.__autoSaveExactRecord(exactMatchRecords)
        return map
    
    
    def __autoSaveExactRecord(self, map):
        if map:
            for authorName in map.keySet():
                authorDocs = map.get(authorName)
                for doc in authorDocs:
                    id = doc.get("id")
                    name = doc.getList("dc_title").get(0)
                    title = doc.getList("dc_description").get(0)
                    handle = doc.getList("handle").get(0)
                    faculty = doc.getList("faculty").get(0)
                    school = doc.getList("school").get(0)
                    hash = self.getHash(name)
                    
                    self.__manifest.set("manifest/node-%s/title" % (hash), name)
                    self.__manifest.set("manifest/node-%s/children/node-%s/id" % (hash, id), id)
                    self.__manifest.set("manifest/node-%s/children/node-%s/title" % (hash, id), title)
                    if handle:
                        self.__manifest.set("manifest/node-%s/children/node-%s/handle" % (hash, id), handle)
                    if faculty:
                        self.__manifest.set("manifest/node-%s/children/node-%s/faculty" % (hash, id), faculty)
                    if school:
                        self.__manifest.set("manifest/node-%s/children/node-%s/school" % (hash, id), school)
                self.__saveManifest(self.__oid)
    
    def __getMetadata(self, oid):
        req = SearchRequest('id:%s' % oid)
        req.setParam("fq", 'item_type:"object"')
        
        # Make sure 'fq' has already been set in the session
        ##security_roles = self.authentication.get_roles_list();
        ##security_query = 'security_filter:("' + '" OR "'.join(security_roles) + '")'
        ##req.addParam("fq", security_query)
        
        out = ByteArrayOutputStream()
        indexer = self.services.getIndexer()
        indexer.search(req, out)
        result = JsonConfigHelper(ByteArrayInputStream(out.toByteArray()))
        #self.log.info("result={}", result.toString())
        return result.getJsonList("response/docs").get(0)
    
    def getRank(self, score):
        return "%.2f" % (min(1.0, float(score)) * 100)
    
    def getMetadata(self):
        return self.__metadata
    
    def getFormData(self, key):
        return self.formData.get(key, "")
    
    def getManifest(self):
        return self.__manifest.getJsonMap("manifest")
    
    def getPackageTitle(self):
        return StringEscapeUtils.escapeHtml(self.formData.get("title", self.__manifest.get("title")))
    
    def getMeta(self, metaName):
        return StringEscapeUtils.escapeHtml(self.formData.get(metaName, self.__manifest.get(metaName)))
    
    def getManifestViewId(self):
        searchPortal = self.__manifest.get("viewId", self.defaultPortal)
        if self.services.portalManager.exists(searchPortal):
            return searchPortal
        else:
            return self.defaultPortal
    
    def getMimeType(self, oid):
        return self.__getContentType(oid) or ""
    
    def getMimeTypeIcon(self, oid):
        #print " *** getMimeTypeIcon(%s)" % oid
        # check for specific icon
        contentType = self.__getContentType(oid)
        iconPath = "images/icons/mimetype/%s/icon.png" % contentType
        resource = self.services.getPageService().resourceExists(self.portalId, iconPath)
        if resource is not None:
            return iconPath
        elif contentType is not None and contentType.find("/") != -1:
            # check for major type
            iconPath = "images/icons/mimetype/%s/icon.png" % contentType[:contentType.find("/")]
            resource = self.services.getPageService().resourceExists(self.portalId, iconPath)
            if resource is not None:
                return iconPath
        # use default icon
        return "images/icons/mimetype/icon.png"
    
    def __getContentType(self, oid):
        #print " *** __getContentType(%s)" % oid
        contentType = ""
        if oid == "blank":
            contentType = "application/x-fascinator-blank-node"
        else:
            object = self.services.getStorage().getObject(oid)
            sourceId = object.getSourceId()
            payload = object.getPayload(sourceId)
            contentType = payload.getContentType()
            payload.close()
            object.close()
        return contentType
    
    def __readManifest(self, oid):
        object = self.services.getStorage().getObject(oid)
        sourceId = object.getSourceId()
        payload = object.getPayload(sourceId)
        payloadReader = InputStreamReader(payload.open(), "UTF-8")
        manifest = JsonConfigHelper(payloadReader)
        payloadReader.close()
        payload.close()
        object.close()
        return manifest
    
    def __addNode(self):
        print self.__manifest.toString()
        return "{}"
    
    def __saveManifest(self, oid):
        object = self.services.getStorage().getObject(oid)
        sourceId = object.getSourceId()
        manifestStr = String(self.__manifest.toString())
        object.updatePayload(sourceId,
                             ByteArrayInputStream(manifestStr.getBytes("UTF-8")))
        object.close()

    def __searchNames(self, searchText):
        # search common forms
        lookupNames = []
        
        req = SearchRequest('(dc_title:"%s")^2.5' % searchText)
        self.log.info("searchNames query={}", req.query)
        req.setParam("fq", 'recordtype:"author"')
        req.addParam("fq", 'item_type:"object"')
        req.setParam("rows", "9999")
        req.setParam("fl", "score")
        req.setParam("sort", "score desc")
        
        # Make sure 'fq' has already been set in the session
        ##security_roles = self.authentication.get_roles_list();
        ##security_query = 'security_filter:("' + '" OR "'.join(security_roles) + '")'
        ##req.addParam("fq", security_query)
        
        out = ByteArrayOutputStream()
        indexer = self.services.getIndexer()
        indexer.search(req, out)
        result = JsonConfigHelper(ByteArrayInputStream(out.toByteArray()))
        
        #self.log.info("result={}", result.toString())
        docs = result.getJsonList("response/docs")
        return docs
        map = LinkedHashMap()
        for doc in docs:
            authorName = doc.getList("dc_title").get(0)
            if map.containsKey(authorName):
                authorDocs = map.get(authorName)
            else:
                authorDocs = ArrayList()
                map.put(authorName, authorDocs)
            authorDocs.add(doc)
        
        #might not need this....
        self.__maxScore = max(1.0, float(result.get("response/maxScore")))
        print map
        return map